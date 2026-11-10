from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from mooc.domain.events import Event, EventType
from mooc.domain.market import Bar, VolatilityPoint
from mooc.services import scanner
from mooc.services.volatility import VolatilitySummary

NOW = datetime(2026, 11, 9, 20, 0, tzinfo=UTC)


def _bars(closes: list[float]) -> list[Bar]:
    start = date(2026, 1, 1)
    return [
        Bar(day=start + timedelta(days=index), close=close) for index, close in enumerate(closes)
    ]


def test_trend_strong_bullish_and_unknown():
    rising = _bars([100 + index for index in range(60)])
    trend = scanner.assess_trend(rising)
    assert trend.label == "strong_bullish"
    assert trend.above_ma20 is True and trend.above_ma50 is True

    assert scanner.assess_trend(_bars([100, 101])).label == "unknown"


def test_trend_bearish():
    falling = _bars([200 - index for index in range(60)])
    assert scanner.assess_trend(falling).label == "strong_bearish"


def test_volatility_regime_from_iv_rank():
    def summary(rank: float | None) -> VolatilitySummary:
        return VolatilitySummary(
            iv=30.0, hv=20.0, iv_rank=rank, iv_percentile=None, iv_hv_diff=10.0
        )

    assert scanner.assess_volatility(summary(85.0)).regime == "high"
    assert scanner.assess_volatility(summary(50.0)).regime == "neutral"
    assert scanner.assess_volatility(summary(10.0)).regime == "low"
    assert scanner.assess_volatility(summary(None)).regime is None


def test_event_risk_levels():
    earnings = Event(
        event_type=EventType.EARNINGS,
        event_datetime=NOW + timedelta(days=3),
        observed_at=NOW,
        code="US.AAPL",
    )
    macro = Event(
        event_type=EventType.ECONOMIC,
        event_datetime=NOW + timedelta(days=2),
        observed_at=NOW,
    )
    assert scanner.assess_events([earnings], now=NOW).risk == "high"
    assert scanner.assess_events([earnings], now=NOW).days_to_earnings == 3
    assert scanner.assess_events([macro], now=NOW).risk == "medium"
    assert scanner.assess_events([], now=NOW).risk == "low"
    far = Event(
        event_type=EventType.EARNINGS,
        event_datetime=NOW + timedelta(days=30),
        observed_at=NOW,
    )
    assert scanner.assess_events([far], now=NOW).risk == "low"


def test_liquidity_undetermined_when_threshold_missing():
    assert scanner.assess_liquidity(underlying_volume=None).ok is None
    assert scanner.assess_liquidity(underlying_volume=100).ok is None
    assert scanner.assess_liquidity(underlying_volume=100, min_volume=50).ok is True
    assert scanner.assess_liquidity(underlying_volume=10, min_volume=50).ok is False


def test_scan_collects_missing_data():
    result = scanner.scan(
        bars=_bars([100, 101]),
        volatility_points=[VolatilityPoint(day=date(2026, 11, 7))],
        events=[],
        now=NOW,
    )
    assert result.trend.label == "unknown"
    assert "trend: insufficient price history" in result.missing_data
    assert "volatility: iv_rank unavailable" in result.missing_data
    assert "liquidity: undetermined" in result.missing_data
