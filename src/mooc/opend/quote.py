"""Market snapshot access (last price / bid / ask) built on ``moomoo-api``."""

from __future__ import annotations

from .client import OpendClient
from .values import require_ok as _require_ok
from .values import to_float as _num


def last_prices(client: OpendClient, codes: list[str]) -> dict[str, float | None]:
    """Return the latest price for each code (``None`` when unavailable)."""
    if not codes:
        return {}
    ret, data = client.quote_ctx.get_market_snapshot(codes)
    _require_ok("get_market_snapshot", ret, data)
    prices: dict[str, float | None] = {}
    for _, row in data.iterrows():
        prices[str(row.get("code"))] = _num(row.get("last_price"))
    return prices


def bid_ask(client: OpendClient, codes: list[str]) -> dict[str, tuple[float | None, float | None]]:
    """Return ``(bid_price, ask_price)`` for each code."""
    if not codes:
        return {}
    ret, data = client.quote_ctx.get_market_snapshot(codes)
    _require_ok("get_market_snapshot", ret, data)
    quotes: dict[str, tuple[float | None, float | None]] = {}
    for _, row in data.iterrows():
        quotes[str(row.get("code"))] = (_num(row.get("bid_price")), _num(row.get("ask_price")))
    return quotes
