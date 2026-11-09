"""Market snapshot access (last price / bid / ask) built on ``moomoo-api``.

``stock_snapshot`` returns provenance-aware quotes: ``observed_at`` is derived
from the vendor ``update_time`` (US market == America/New_York) so a closed
market or delayed feed is flagged stale instead of being reported as fresh.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from ..domain.market import DataSource, StockQuote, quality_for
from .client import OpendClient
from .values import require_ok as _require_ok
from .values import to_float as _num
from .values import to_int as _int

_US_EASTERN = ZoneInfo("America/New_York")
_UPDATE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _update_time(value) -> datetime | None:
    if not value:
        return None
    try:
        naive = datetime.strptime(str(value), _UPDATE_TIME_FORMAT)
    except ValueError:
        return None
    return naive.replace(tzinfo=_US_EASTERN).astimezone(UTC)


def stock_snapshot(
    client: OpendClient,
    codes: list[str],
    *,
    now: datetime,
    max_age_seconds: float,
) -> dict[str, StockQuote]:
    """Return provenance-aware snapshots keyed by code."""
    if not codes:
        return {}
    ret, data = client.quote_ctx.get_market_snapshot(codes)
    _require_ok("get_market_snapshot", ret, data)
    quotes: dict[str, StockQuote] = {}
    for _, row in data.iterrows():
        code = str(row.get("code"))
        update = _update_time(row.get("update_time"))
        missing = () if update is not None else ("update_time",)
        quotes[code] = StockQuote(
            code=code,
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
            volume=_int(row.get("volume")),
            update_time=update,
        )
    return quotes


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
