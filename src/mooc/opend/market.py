"""Underlying price history and market state (read-only) via ``moomoo-api``."""

from __future__ import annotations

from datetime import date

from ..domain.market import Bar
from .client import OpendClient
from .values import require_ok as _require_ok
from .values import to_float as _num
from .values import to_int as _int

__all__ = ["history_kline", "market_state"]

_MAX_BARS = 1000


def _parse_day(value) -> date:
    return date.fromisoformat(str(value)[:10])


def history_kline(
    client: OpendClient,
    code: str,
    *,
    start: str,
    end: str,
) -> list[Bar]:
    """Return daily bars for ``code`` in ``[start, end]`` (ascending)."""
    from moomoo import KLType

    bars: list[Bar] = []
    page = None
    while True:
        ret, data, page = client.quote_ctx.request_history_kline(
            code, start=start, end=end, ktype=KLType.K_DAY, max_count=_MAX_BARS, page_req_key=page
        )
        _require_ok("request_history_kline", ret, data)
        for _, row in data.iterrows():
            bars.append(
                Bar(
                    day=_parse_day(row.get("time_key")),
                    close=_num(row.get("close")),
                    open=_num(row.get("open")),
                    high=_num(row.get("high")),
                    low=_num(row.get("low")),
                    volume=_int(row.get("volume")),
                )
            )
        if page is None:
            break
    return sorted(bars, key=lambda bar: bar.day)


def market_state(client: OpendClient, codes: list[str]) -> dict[str, str]:
    """Return the market session state keyed by code."""
    if not codes:
        return {}
    ret, data = client.quote_ctx.get_market_state(codes)
    _require_ok("get_market_state", ret, data)
    return {str(row.get("code")): str(row.get("market_state")) for _, row in data.iterrows()}
