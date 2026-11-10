"""Scanner: pure trend, volatility, event, and liquidity assessments (spec ch. 3).

No SDK or I/O — callers pass in already-fetched bars, volatility points, events,
and snapshot volume. Insufficient inputs yield an explicit "unknown"/unavailable
assessment rather than a guess.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from ..domain.events import Event, EventType
from ..domain.market import Bar, VolatilityPoint
from .volatility import VolatilitySummary, summarize

__all__ = [
    "EventAssessment",
    "LiquidityAssessment",
    "ScanResult",
    "TrendAssessment",
    "VolatilityAssessment",
    "assess_events",
    "assess_liquidity",
    "assess_trend",
    "assess_volatility",
    "scan",
]

MA_SHORT = 20
MA_LONG = 50
IV_RANK_HIGH = 70.0
IV_RANK_LOW = 30.0
EVENT_HORIZON_DAYS = 7


@dataclass(frozen=True)
class TrendAssessment:
    label: str  # strong_bullish | bullish | neutral | bearish | strong_bearish | unknown
    above_ma20: bool | None = None
    above_ma50: bool | None = None
    ma20: float | None = None
    ma50: float | None = None
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class VolatilityAssessment:
    regime: str | None  # high | neutral | low
    summary: VolatilitySummary
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class EventAssessment:
    risk: str  # high | medium | low
    days_to_earnings: int | None = None
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class LiquidityAssessment:
    ok: bool | None = None
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScanResult:
    trend: TrendAssessment
    volatility: VolatilityAssessment
    event: EventAssessment
    liquidity: LiquidityAssessment
    missing_data: tuple[str, ...] = field(default_factory=tuple)


def _sma(values: Sequence[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def assess_trend(bars: Sequence[Bar]) -> TrendAssessment:
    """Classify the daily trend from moving averages (spec 3.1A)."""
    closes = [bar.close for bar in bars if bar.close is not None]
    if len(closes) < MA_LONG:
        return TrendAssessment("unknown", evidence=(f"insufficient bars ({len(closes)})",))
    last = closes[-1]
    ma20 = _sma(closes, MA_SHORT)
    ma50 = _sma(closes, MA_LONG)
    assert ma20 is not None and ma50 is not None  # guaranteed by the length check
    above20 = last > ma20
    above50 = last > ma50
    if above20 and above50 and ma20 > ma50:
        label = "strong_bullish"
    elif above20 and above50:
        label = "bullish"
    elif not above20 and not above50 and ma20 < ma50:
        label = "strong_bearish"
    elif not above20 and not above50:
        label = "bearish"
    else:
        label = "neutral"
    evidence = (f"close={last:.2f}", f"ma20={ma20:.2f}", f"ma50={ma50:.2f}")
    return TrendAssessment(label, above20, above50, ma20, ma50, evidence)


def assess_volatility(summary: VolatilitySummary) -> VolatilityAssessment:
    """Label the volatility regime from IV Rank (spec 3.1B)."""
    rank = summary.iv_rank
    if rank is None:
        return VolatilityAssessment(None, summary, ("iv_rank unavailable",))
    if rank >= IV_RANK_HIGH:
        regime = "high"
    elif rank <= IV_RANK_LOW:
        regime = "low"
    else:
        regime = "neutral"
    return VolatilityAssessment(regime, summary, (f"iv_rank={rank:.1f}", f"iv={summary.iv}"))


def assess_events(
    events: Sequence[Event], *, now: datetime, horizon_days: int = EVENT_HORIZON_DAYS
) -> EventAssessment:
    """Flag earnings/macro risk within the horizon (spec 3.1C)."""
    horizon = horizon_days
    earnings = [
        event
        for event in events
        if event.event_type is EventType.EARNINGS
        and now <= event.event_datetime
        and (event.event_datetime - now).days <= horizon
    ]
    if earnings:
        nearest = min(earnings, key=lambda event: event.event_datetime)
        days = (nearest.event_datetime - now).days
        return EventAssessment("high", days, (f"earnings in {days}d",))
    macro = [
        event
        for event in events
        if event.event_type is EventType.ECONOMIC
        and now <= event.event_datetime
        and (event.event_datetime - now).days <= horizon
    ]
    if macro:
        return EventAssessment("medium", None, ("macro event in window",))
    return EventAssessment("low", None, ())


def assess_liquidity(
    *, underlying_volume: int | None, min_volume: float | None = None
) -> LiquidityAssessment:
    """Assess tradability; ``min_volume`` undetermined means "cannot conclude" (spec 3.1D)."""
    if underlying_volume is None:
        return LiquidityAssessment(None, ("underlying volume unavailable",))
    if min_volume is None:
        return LiquidityAssessment(None, (f"volume={underlying_volume}", "min_volume undetermined"))
    return LiquidityAssessment(
        underlying_volume >= min_volume, (f"volume={underlying_volume}", f"min={min_volume}")
    )


def scan(
    *,
    bars: Sequence[Bar],
    volatility_points: Sequence[VolatilityPoint],
    events: Sequence[Event],
    now: datetime,
    underlying_volume: int | None = None,
    min_volume: float | None = None,
    lookback: int | None = None,
) -> ScanResult:
    """Run all four screens and collect what could not be determined."""
    summary = (
        summarize(volatility_points)
        if lookback is None
        else summarize(volatility_points, lookback=lookback)
    )
    trend = assess_trend(bars)
    volatility = assess_volatility(summary)
    event = assess_events(events, now=now)
    liquidity = assess_liquidity(underlying_volume=underlying_volume, min_volume=min_volume)

    missing: list[str] = []
    if trend.label == "unknown":
        missing.append("trend: insufficient price history")
    if volatility.regime is None:
        missing.append("volatility: iv_rank unavailable")
    if liquidity.ok is None:
        missing.append("liquidity: undetermined")
    return ScanResult(trend, volatility, event, liquidity, tuple(missing))
