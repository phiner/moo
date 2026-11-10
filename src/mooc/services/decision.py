"""Decision engine: evaluate a strategy rule against scanned inputs (spec 14).

Pure and side-effect free. Any rule field that is present but ``null`` is treated
as undetermined, so the strategy yields NO TRADE with an explicit reason naming
the missing parameters (spec ch. 18 — never invent a value).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.decision import DecisionOutput, TradeStatus
from ..domain.rules import UNSET, Maybe, StrategyRule, Unset
from ..domain.strategy import StrategyType

__all__ = ["StrategyInputs", "build_output", "evaluate_strategy"]

_STRATEGIES = {member.value: member for member in StrategyType}


def _bound(value: Maybe) -> tuple[bool, float | None]:
    """Return ``(specified, number)``; ``specified`` is False for an absent key."""
    if isinstance(value, Unset):
        return False, None
    return True, value


@dataclass(frozen=True)
class StrategyInputs:
    """Metrics the scanner provides; ``None`` means "not available"."""

    market_regime: str | None = None
    iv_rank: float | None = None
    iv_percentile: float | None = None
    dte: float | None = None
    delta: float | None = None
    width: float | None = None
    data_quality: str = "valid"


def _violations(rule: StrategyRule, inputs: StrategyInputs) -> list[str]:
    reasons: list[str] = []

    regimes = rule.allowed_regimes
    if not isinstance(regimes, Unset):
        if inputs.market_regime is None:
            reasons.append("market_regime unavailable")
        elif regimes is None:
            reasons.append("market_regime undetermined")
        elif inputs.market_regime not in regimes:
            reasons.append(f"market_regime {inputs.market_regime!r} not in {list(regimes)}")

    checks: tuple[tuple[str, Maybe, Maybe], ...] = (
        ("iv_rank", rule.iv_rank_min, rule.iv_rank_max),
        ("iv_percentile", rule.iv_percentile_min, UNSET),
        ("dte", rule.min_dte, rule.max_dte),
        ("delta", rule.delta_min, rule.delta_max),
        ("width", rule.min_width, rule.max_width),
    )
    for label, lower, upper in checks:
        has_lower, low = _bound(lower)
        has_upper, high = _bound(upper)
        if not has_lower and not has_upper:
            continue
        actual = getattr(inputs, label)
        if actual is None:
            reasons.append(f"{label} unavailable")
            continue
        if has_lower and low is not None and actual < low:
            reasons.append(f"{label} {actual} below min {low}")
        if has_upper and high is not None and actual > high:
            reasons.append(f"{label} {actual} above max {high}")
    return reasons


def evaluate_strategy(rule: StrategyRule, inputs: StrategyInputs) -> list[str]:
    """Return rejection reasons; empty list means the strategy is actionable."""
    if not rule.enabled:
        return [f"strategy {rule.name!r} is disabled"]
    undetermined = rule.undetermined()
    if undetermined:
        return [f"undetermined (null): {name}" for name in undetermined]
    return _violations(rule, inputs)


def build_output(
    rule: StrategyRule,
    inputs: StrategyInputs,
    *,
    symbol: str,
    timestamp: str,
) -> DecisionOutput:
    """Assemble the standard 14.1 output for ``rule`` against ``inputs``."""
    reasons = evaluate_strategy(rule, inputs)
    strategy = _STRATEGIES.get(rule.name)
    actionable = not reasons and strategy is not None

    if strategy is None and not reasons:
        reasons = [f"unknown strategy {rule.name!r}"]

    strategy_block: dict[str, object] = {
        "type": rule.name,
        "expiration": None,
        "short_strike": None,
        "long_strike": None,
        "net_credit": None,
        "max_profit": None,
        "max_loss": None,
        "breakeven": None,
    }
    risk_specified, risk_value = _bound(rule.max_account_risk_pct)
    risk_block: dict[str, object] = {
        "max_account_risk_pct": risk_value if risk_specified else None,
        "allowed_risk": None,
        "recommended_contracts": None,
        "portfolio_risk_passed": False,
    }
    exit_conditions = [
        name
        for name, value in (
            ("take_profit_pct", rule.take_profit_pct),
            ("stop_review_multiple", rule.stop_review_multiple),
            ("time_exit_dte", rule.time_exit_dte),
        )
        if not isinstance(value, Unset) and value is not None
    ]
    return DecisionOutput(
        symbol=symbol,
        analysis_timestamp=timestamp,
        data_quality=inputs.data_quality,
        market_regime=inputs.market_regime,
        volatility_regime=None,
        event_risk=None,
        recommended_action=f"consider_{rule.name}" if actionable else "no_trade",
        trade_status=TradeStatus.CANDIDATE if actionable else TradeStatus.REJECTED,
        strategy=strategy_block,
        risk=risk_block,
        entry_conditions=[],
        exit_conditions=exit_conditions,
        rejection_reasons=reasons,
        missing_data=list(rule.undetermined()),
    )
