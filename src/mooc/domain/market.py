"""Market data domain types: provenance, freshness, and quote payloads.

Pure data only — no SDK, storage, or I/O. Every market value carried through the
system is accompanied by :class:`QuoteQuality` so downstream code can tell
realtime from delayed/historical/simulated and detect stale or missing data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

__all__ = [
    "Bar",
    "DataSource",
    "OptionSnapshot",
    "QuoteQuality",
    "StockQuote",
    "VolatilityPoint",
    "is_stale",
    "quality_for",
    "to_utc",
]


class DataSource(StrEnum):
    """Where a value came from. Never conflate these (spec principle 7)."""

    REALTIME = "realtime"
    DELAYED = "delayed"
    HISTORICAL = "historical"
    SIMULATED = "simulated"
    UNKNOWN = "unknown"


def to_utc(value: datetime) -> datetime:
    """Normalize ``value`` to timezone-aware UTC (naive values are assumed UTC)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def is_stale(observed_at: datetime, *, now: datetime, max_age_seconds: float) -> bool:
    """True when ``observed_at`` is older than ``max_age_seconds`` before ``now``."""
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")
    return (to_utc(now) - to_utc(observed_at)).total_seconds() > max_age_seconds


@dataclass(frozen=True)
class QuoteQuality:
    """Provenance and freshness attached to every market value."""

    source: DataSource
    observed_at: datetime
    is_stale: bool = False
    missing_fields: tuple[str, ...] = ()


def quality_for(
    source: DataSource,
    observed_at: datetime,
    *,
    now: datetime,
    max_age_seconds: float,
    missing_fields: tuple[str, ...] = (),
) -> QuoteQuality:
    """Build a :class:`QuoteQuality`, computing staleness from the inputs."""
    return QuoteQuality(
        source=source,
        observed_at=to_utc(observed_at),
        is_stale=is_stale(observed_at, now=now, max_age_seconds=max_age_seconds),
        missing_fields=tuple(missing_fields),
    )


@dataclass(frozen=True)
class StockQuote:
    """One underlying snapshot (last/bid/ask) with provenance."""

    code: str
    quality: QuoteQuality
    last: float | None = None
    bid: float | None = None
    ask: float | None = None
    volume: int | None = None
    update_time: datetime | None = None


@dataclass(frozen=True)
class Bar:
    """One daily OHLCV bar (from ``request_history_kline``)."""

    day: date
    close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int | None = None


@dataclass(frozen=True)
class VolatilityPoint:
    """One day of an underlying's IV/HV history (from ``his_volatility``)."""

    day: date
    iv: float | None = None
    hv: float | None = None
    underlying_price: float | None = None


@dataclass(frozen=True)
class OptionSnapshot:
    """One option contract snapshot (quotes + Greeks) with provenance."""

    code: str
    underlying: str
    quality: QuoteQuality
    last: float | None = None
    bid: float | None = None
    ask: float | None = None
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None
    open_interest: int | None = None
    volume: int | None = None
    update_time: datetime | None = None
