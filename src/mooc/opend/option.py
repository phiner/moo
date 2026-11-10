"""Option data access built on the official ``moomoo-api`` SDK.

Only combo-level bid1/ask1 from ``get_option_strategy_analysis`` is authoritative
for combo pricing; never derive it from single-leg quotes.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from ..domain.market import DataSource, OptionSnapshot, quality_for
from ..domain.options import (
    ComboAnalysis,
    OptionChain,
    OptionContract,
    OptionLeg,
    OptionQuote,
    OptionType,
)
from .client import OpendClient
from .errors import OpendRejected
from .quote import parse_update_time as _parse_update_time
from .values import require_ok as _require_ok
from .values import to_float as _num
from .values import to_int as _int

_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _to_sdk_legs(legs: list[OptionLeg]):
    from moomoo import OptionStrategyLeg

    out = []
    for leg in legs:
        sdk = OptionStrategyLeg()
        sdk.code = leg.code
        sdk.action = leg.action.value
        sdk.quantity = float(leg.quantity)
        out.append(sdk)
    return out


def _parse_date(value) -> date:
    match = _DATE_RE.search(str(value))
    if not match:
        raise ValueError(f"unparseable date: {value!r}")
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _parse_float_list(value) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", str(value))]


# -- public API -----------------------------------------------------------
def list_expirations(client: OpendClient, underlying: str) -> list[str]:
    """Return available expiration dates (ISO ``YYYY-MM-DD``) for ``underlying``."""
    ret, data = client.quote_ctx.get_option_expiration_date(underlying)
    _require_ok("get_option_expiration_date", ret, data)
    return [_parse_date(value).isoformat() for value in data["strike_time"].tolist()]


def get_chain(
    client: OpendClient,
    underlying: str,
    start: str | None = None,
    end: str | None = None,
    option_type: str = "ALL",
) -> OptionChain:
    """Fetch an option chain for a date range (defaults applied by OpenD)."""
    ret, data = client.quote_ctx.get_option_chain(
        underlying, start=start, end=end, option_type=option_type
    )
    _require_ok("get_option_chain", ret, data)
    contracts = [
        OptionContract(
            code=str(row["code"]),
            underlying=str(row.get("stock_owner", underlying)),
            expiry=_parse_date(row["strike_time"]),
            strike=float(row["strike_price"]),
            option_type=OptionType(str(row["option_type"]).upper()),
            multiplier=int(row.get("lot_size", 100) or 100),
        )
        for _, row in data.iterrows()
    ]
    return OptionChain(underlying=underlying, contracts=contracts)


def get_quote(client: OpendClient, legs: list[OptionLeg]) -> list[OptionQuote]:
    """Single-leg / multi-leg snapshot (last price + Greeks). Not combo bid/ask."""
    ret, data = client.quote_ctx.get_option_quote(_to_sdk_legs(legs))
    _require_ok("get_option_quote", ret, data)
    quotes = []
    for leg, (_, row) in zip(legs, data.iterrows(), strict=False):
        quotes.append(
            OptionQuote(
                code=leg.code,
                last=_num(row.get("price")),
                iv=_num(row.get("implied_volatility")),
                delta=_num(row.get("delta")),
                gamma=_num(row.get("gamma")),
                theta=_num(row.get("theta")),
                vega=_num(row.get("vega")),
                rho=_num(row.get("rho")),
                oi=_int(row.get("open_interest")),
                volume=_int(row.get("volume")),
            )
        )
    return quotes


def snapshots(
    client: OpendClient,
    codes: list[str],
    *,
    now: datetime,
    max_age_seconds: float,
) -> dict[str, OptionSnapshot]:
    """Return per-contract snapshots (bid/ask + Greeks) keyed by code.

    ``get_market_snapshot`` carries option fields (delta/IV/OI) for many codes in
    one call — unlike ``get_option_quote``, which caps combo legs at 4.
    """
    if not codes:
        return {}
    ret, data = client.quote_ctx.get_market_snapshot(codes)
    _require_ok("get_market_snapshot", ret, data)
    result: dict[str, OptionSnapshot] = {}
    for _, row in data.iterrows():
        code = str(row.get("code"))
        update = _parse_update_time(row.get("update_time"))
        missing = () if update is not None else ("update_time",)
        result[code] = OptionSnapshot(
            code=code,
            underlying=str(row.get("stock_owner") or ""),
            quality=quality_for(
                DataSource.REALTIME,
                update or now,
                now=now,
                max_age_seconds=max_age_seconds,
                missing_fields=missing,
            ),
            last=_num(row.get("last_price")),
            bid=_num(row.get("bid_price")),
            ask=_num(row.get("ask_price")),
            iv=_num(row.get("option_implied_volatility")),
            delta=_num(row.get("option_delta")),
            gamma=_num(row.get("option_gamma")),
            theta=_num(row.get("option_theta")),
            vega=_num(row.get("option_vega")),
            rho=_num(row.get("option_rho")),
            open_interest=_int(row.get("option_open_interest")),
            volume=_int(row.get("volume")),
            update_time=update,
        )
    return result


def combo_analysis(client: OpendClient, legs: list[OptionLeg]) -> ComboAnalysis:
    """Authoritative combo bid1/ask1 and P&L for a set of legs."""
    ret, data = client.quote_ctx.get_option_strategy_analysis(_to_sdk_legs(legs))
    _require_ok("get_option_strategy_analysis", ret, data)
    if len(data) == 0:
        raise OpendRejected("get_option_strategy_analysis", "empty result")
    row = data.iloc[0]
    return ComboAnalysis(
        legs=legs,
        code=str(row.get("code", "")),
        name=str(row.get("name", "")),
        strategy=str(row.get("option_strategy", "")),
        bid1=float(row["bid1"]),
        ask1=float(row["ask1"]),
        max_profit=float(row["max_profit"]),
        max_loss=float(row["max_loss"]),
        breakeven=_parse_float_list(row.get("breakeven_points", "")),
        prob_profit=float(row.get("prob_of_profit", 0.0) or 0.0),
        delta=float(row.get("delta", 0.0) or 0.0),
        theta=float(row.get("theta", 0.0) or 0.0),
    )
