"""Watchlist (moomoo self-selected groups) access + option summaries.

Read-only: groups and their members come from ``get_user_security_group`` /
``get_user_security``; the summary reuses the option chain and a market snapshot.

OpenD throttles ``GetOptionChain`` to 10 calls per rolling 30 seconds, so chain
calls pass through a process-wide sliding-window limiter and are retried when
they still hit the frequency limit. The daemon is the sole SDK owner, so this
limiter is global.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import date

from ..domain.options import OptionType
from ..domain.watchlist import Security, UnderlyingSummary, WatchlistGroup
from .client import OpendClient
from .errors import OpendRejected
from .quote import bid_ask, last_prices
from .values import require_ok as _require_ok

# Security types that can carry an option chain worth summarizing.
TRADABLE_TYPES = frozenset({"STOCK", "ETF", "IDX"})
# One batch == one option-chain window, so callers page 10 underlyings at a time.
DEFAULT_LIMIT = 10

# OpenD: "Maximum 10 times per 30 seconds" for GetOptionChain.
_CHAIN_CAPACITY = 10
_CHAIN_WINDOW_SECONDS = 30.0
_CHAIN_RETRY_ATTEMPTS = 3


def _text(value) -> str:
    return "" if value is None else str(value)


class _SlidingWindow:
    """Process-wide limiter matching OpenD's rolling-window quota."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._times: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            while True:
                now = time.monotonic()
                while self._times and now - self._times[0] >= self._window:
                    self._times.popleft()
                if len(self._times) < self._limit:
                    self._times.append(now)
                    return
                time.sleep(max(self._window - (now - self._times[0]), 0.05))


_chain_bucket = _SlidingWindow(_CHAIN_CAPACITY, _CHAIN_WINDOW_SECONDS)


def _is_frequency_error(exc: Exception) -> bool:
    return "frequency" in str(exc).lower()


def list_groups(client: OpendClient) -> list[WatchlistGroup]:
    """Return all self-selected groups (custom and system)."""
    from moomoo import UserSecurityGroupType

    ret, data = client.quote_ctx.get_user_security_group(UserSecurityGroupType.ALL)
    _require_ok("get_user_security_group", ret, data)
    return [
        WatchlistGroup(name=_text(row.get("group_name")), group_type=_text(row.get("group_type")))
        for _, row in data.iterrows()
    ]


def list_group_members(client: OpendClient, group_name: str) -> list[Security]:
    """Return the tradable-underlying members of ``group_name``."""
    ret, data = client.quote_ctx.get_user_security(group_name)
    _require_ok("get_user_security", ret, data)
    members: list[Security] = []
    for _, row in data.iterrows():
        stock_type = _text(row.get("stock_type"))
        if stock_type not in TRADABLE_TYPES:
            continue
        members.append(
            Security(
                code=_text(row.get("code")),
                name=_text(row.get("name")),
                stock_type=stock_type,
            )
        )
    return members


def _nearest_expiry(dates: list[str]) -> str | None:
    today = date.today().isoformat()
    return next((value for value in dates if value >= today), None)


def _pick_atm_strike(strikes: list[float], price: float | None) -> float | None:
    if not strikes:
        return None
    if price is None:
        ordered = sorted(strikes)
        return ordered[len(ordered) // 2]
    return min(strikes, key=lambda strike: abs(strike - price))


def _get_chain(client: OpendClient, code: str, start: str, end: str):
    from . import option

    last: OpendRejected | None = None
    for _ in range(_CHAIN_RETRY_ATTEMPTS):
        _chain_bucket.acquire()
        try:
            return option.get_chain(client, code, start=start, end=end)
        except OpendRejected as exc:
            if not _is_frequency_error(exc):
                raise
            last = exc
    assert last is not None
    raise last


@dataclass
class _Draft:
    code: str
    name: str
    last_price: float | None
    expiry: str | None = None
    atm_strike: float | None = None
    call: str | None = None
    put: str | None = None


def _draft_for(client: OpendClient, member: Security, price: float | None) -> _Draft:
    from . import option

    draft = _Draft(code=member.code, name=member.name, last_price=price)
    try:
        expiry = _nearest_expiry(option.list_expirations(client, member.code))
        if expiry is None:
            return draft
        chain = _get_chain(client, member.code, expiry, expiry)
        strikes = sorted({c.strike for c in chain.contracts})
        strike = _pick_atm_strike(strikes, price)
        if strike is None:
            return draft
        draft.expiry = expiry
        draft.atm_strike = strike
        for contract in chain.contracts:
            if contract.strike != strike:
                continue
            if contract.option_type is OptionType.CALL:
                draft.call = contract.code
            elif contract.option_type is OptionType.PUT:
                draft.put = contract.code
    except OpendRejected:
        return draft  # no option chain for this underlying: leave the summary blank
    return draft


def _finalize(
    draft: _Draft, quotes: dict[str, tuple[float | None, float | None]]
) -> UnderlyingSummary:
    call_bid, call_ask = quotes.get(draft.call or "", (None, None))
    put_bid, put_ask = quotes.get(draft.put or "", (None, None))
    return UnderlyingSummary(
        code=draft.code,
        name=draft.name,
        last_price=draft.last_price,
        expiry=draft.expiry,
        atm_strike=draft.atm_strike,
        call_bid=call_bid,
        call_ask=call_ask,
        put_bid=put_bid,
        put_ask=put_ask,
    )


def summarize_underlying(client: OpendClient, member: Security) -> UnderlyingSummary:
    """Build the nearest-expiry ATM summary for a single member."""
    price = last_prices(client, [member.code]).get(member.code)
    draft = _draft_for(client, member, price)
    codes = [code for code in (draft.call, draft.put) if code]
    return _finalize(draft, bid_ask(client, codes))


def group_option_summaries(
    client: OpendClient,
    members: list[Security],
    limit: int = DEFAULT_LIMIT,
) -> list[UnderlyingSummary]:
    """Build nearest-expiry ATM summaries for up to ``limit`` members."""
    selected = members[:limit]
    prices = last_prices(client, [member.code for member in selected])
    drafts = [_draft_for(client, member, prices.get(member.code)) for member in selected]
    atm_codes = [code for draft in drafts for code in (draft.call, draft.put) if code]
    quotes = bid_ask(client, atm_codes)
    return [_finalize(draft, quotes) for draft in drafts]
