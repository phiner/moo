"""End-to-end analysis for one symbol: fetch inputs, scan, select, evaluate.

Produces the standard decision output (spec 14.1). Where contract-level inputs
(DTE/delta/width) can be derived from the live chain they are fed to the engine
and the strategy block is filled from the pricing module; otherwise the engine
honestly reports them as unavailable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from ..config import AppConfig
from ..domain.decision import DecisionOutput, TradeStatus
from ..domain.market import StockQuote
from ..domain.rules import StrategyRule, Unset
from ..domain.strategy import PricingResult, StrategyType
from ..opend import events as events_api
from ..opend import market as market_api
from ..opend import option as option_api
from ..opend import quote as quote_api
from ..opend import volatility as vol_api
from ..opend.client import OpendClient
from . import decision, pricing, scanner, selector

__all__ = ["analyze_symbol"]

PRICE_HISTORY_DAYS = 180
VOL_HISTORY_DAYS = 364
EVENT_HORIZON_DAYS = 7


def _number(value) -> float | None:
    """Convert a rule tri-state field to a plain number (UNSET/null -> None)."""
    if value is None or isinstance(value, Unset):
        return None
    return float(value)


def _data_quality(snapshot: StockQuote | None) -> str:
    if snapshot is None:
        return "missing"
    return "stale" if snapshot.quality.is_stale else "valid"


def _fetch_selection(
    client: OpendClient,
    symbol: str,
    rule: StrategyRule,
    *,
    now: datetime,
    config: AppConfig,
) -> selector.SelectionOutcome | None:
    shape = selector.shape_for(rule.name)
    if shape is None:
        return None
    option_type, short_is_higher, is_credit = shape
    min_dte = _number(rule.min_dte)
    max_dte = _number(rule.max_dte)
    if min_dte is None or max_dte is None:
        return None

    today = now.date()
    chain = option_api.get_chain(
        client,
        symbol,
        start=(today + timedelta(days=int(min_dte))).isoformat(),
        end=(today + timedelta(days=int(max_dte))).isoformat(),
        option_type=option_type.value,
    )
    contracts = [c for c in chain.contracts if c.option_type is option_type]
    if not contracts:
        return None

    snapshots = option_api.snapshots(
        client,
        [c.code for c in contracts],
        now=now,
        max_age_seconds=config.data_quality.realtime_max_age_sec,
    )

    rows = []
    for contract in contracts:
        snap = snapshots.get(contract.code)
        rows.append(
            selector.ContractQuote(
                code=contract.code,
                expiry=contract.expiry,
                strike=contract.strike,
                option_type=contract.option_type,
                bid=snap.bid if snap is not None else None,
                ask=snap.ask if snap is not None else None,
                delta=snap.delta if snap is not None else None,
                open_interest=snap.open_interest if snap is not None else None,
                volume=snap.volume if snap is not None else None,
            )
        )
    return selector.select_spread(
        rows,
        today=today,
        option_type=option_type,
        short_is_higher=short_is_higher,
        is_credit=is_credit,
        min_dte=min_dte,
        max_dte=max_dte,
        delta_min=_number(rule.delta_min),
        delta_max=_number(rule.delta_max),
        min_width=_number(rule.min_width),
        max_width=_number(rule.max_width),
    )


def _priced(rule_name: str, selection: selector.SpreadSelection) -> PricingResult | None:
    short_bid = selection.short.bid or 0.0
    long_ask = selection.long.ask or 0.0
    if rule_name == StrategyType.BULL_PUT_CREDIT_SPREAD:
        return pricing.bull_put_credit_spread(
            short_strike=selection.short.strike,
            long_strike=selection.long.strike,
            short_bid=short_bid,
            long_ask=long_ask,
        )
    if rule_name == StrategyType.BEAR_CALL_CREDIT_SPREAD:
        return pricing.bear_call_credit_spread(
            short_strike=selection.short.strike,
            long_strike=selection.long.strike,
            short_bid=short_bid,
            long_ask=long_ask,
        )
    if rule_name == StrategyType.BULL_CALL_DEBIT_SPREAD:
        return pricing.bull_call_debit_spread(
            long_strike=selection.long.strike,
            short_strike=selection.short.strike,
            long_ask=long_ask,
            short_bid=short_bid,
        )
    if rule_name == StrategyType.BEAR_PUT_DEBIT_SPREAD:
        return pricing.bear_put_debit_spread(
            long_strike=selection.long.strike,
            short_strike=selection.short.strike,
            long_ask=long_ask,
            short_bid=short_bid,
        )
    return None


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
    outcome = _fetch_selection(client, symbol, rule, now=now, config=config)
    selection = outcome.selection if outcome is not None else None

    inputs = decision.StrategyInputs(
        market_regime=scan_result.trend.label if scan_result.trend.label != "unknown" else None,
        iv_rank=scan_result.volatility.summary.iv_rank,
        iv_percentile=scan_result.volatility.summary.iv_percentile,
        dte=selection.dte if selection is not None else None,
        delta=selection.delta if selection is not None else None,
        width=selection.width if selection is not None else None,
        data_quality=data_quality,
    )
    output = decision.build_output(rule, inputs, symbol=symbol, timestamp=now.isoformat())
    missing = list(dict.fromkeys([*output.missing_data, *scan_result.missing_data]))

    if output.trade_status is TradeStatus.CANDIDATE and selection is not None:
        priced = _priced(rule.name, selection)
        if priced is not None:
            output = replace(
                output,
                strategy={
                    "type": rule.name,
                    "expiration": selection.expiry.isoformat(),
                    "short_strike": selection.short.strike,
                    "long_strike": selection.long.strike,
                    "net_credit": priced.net_premium,
                    "max_profit": priced.max_profit,
                    "max_loss": priced.max_loss,
                    "breakeven": priced.breakeven,
                },
            )
    return replace(
        output,
        volatility_regime=scan_result.volatility.regime,
        event_risk=scan_result.event.risk,
        missing_data=missing,
    )
