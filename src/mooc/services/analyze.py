"""End-to-end analysis for one symbol: fetch inputs, scan, evaluate a rule.

Produces the standard decision output (spec 14.1). Contract-level inputs (DTE,
delta, width) are not yet supplied, so rules that constrain them will honestly
report "unavailable" rather than invent values.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from ..config import AppConfig
from ..domain.decision import DecisionOutput, TradeStatus
from ..domain.market import StockQuote
from ..domain.rules import StrategyRule
from ..opend import events as events_api
from ..opend import market as market_api
from ..opend import quote as quote_api
from ..opend import volatility as vol_api
from ..opend.client import OpendClient
from . import decision, scanner

__all__ = ["analyze_symbol"]

PRICE_HISTORY_DAYS = 180
VOL_HISTORY_DAYS = 364
EVENT_HORIZON_DAYS = 7


def _data_quality(snapshot: StockQuote | None) -> str:
    if snapshot is None:
        return "missing"
    return "stale" if snapshot.quality.is_stale else "valid"


def analyze_symbol(
    client: OpendClient,
    symbol: str,
    *,
    rules: Sequence[StrategyRule],
    config: AppConfig,
    now: datetime | None = None,
) -> DecisionOutput:
    """Analyze ``symbol`` and return a 14.1 decision output."""
    now = now or datetime.now(UTC)
    today = now.date()
    market = config.ui.market

    bars = market_api.history_kline(
        client,
        symbol,
        start=(today - timedelta(days=PRICE_HISTORY_DAYS)).isoformat(),
        end=today.isoformat(),
    )
    points = vol_api.his_volatility(
        client,
        symbol,
        begin=(today - timedelta(days=VOL_HISTORY_DAYS)).isoformat(),
        end=today.isoformat(),
    )
    snapshot = quote_api.stock_snapshot(
        client,
        [symbol],
        now=now,
        max_age_seconds=config.data_quality.realtime_max_age_sec,
    ).get(symbol)
    events = events_api.earnings_calendar(
        client,
        market,
        begin=today.isoformat(),
        end=(today + timedelta(days=EVENT_HORIZON_DAYS)).isoformat(),
        observed_at=now,
    )

    scan_result = scanner.scan(
        bars=bars,
        volatility_points=points,
        events=events,
        now=now,
        underlying_volume=snapshot.volume if snapshot is not None else None,
    )
    data_quality = _data_quality(snapshot)

    enabled = [rule for rule in rules if rule.enabled]
    if not enabled:
        return DecisionOutput(
            symbol=symbol,
            analysis_timestamp=now.isoformat(),
            data_quality=data_quality,
            market_regime=scan_result.trend.label,
            volatility_regime=scan_result.volatility.regime,
            event_risk=scan_result.event.risk,
            recommended_action="no_trade",
            trade_status=TradeStatus.REJECTED,
            rejection_reasons=["no enabled strategy rules configured"],
            missing_data=list(scan_result.missing_data),
        )

    rule = enabled[0]
    inputs = decision.StrategyInputs(
        market_regime=scan_result.trend.label if scan_result.trend.label != "unknown" else None,
        iv_rank=scan_result.volatility.summary.iv_rank,
        iv_percentile=scan_result.volatility.summary.iv_percentile,
        data_quality=data_quality,
    )
    output = decision.build_output(rule, inputs, symbol=symbol, timestamp=now.isoformat())
    missing = list(dict.fromkeys([*output.missing_data, *scan_result.missing_data]))
    return replace(
        output,
        volatility_regime=scan_result.volatility.regime,
        event_risk=scan_result.event.risk,
        missing_data=missing,
    )
