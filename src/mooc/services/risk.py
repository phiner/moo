"""Risk engine: sizing, Greeks aggregation, exit signals, drawdown policy.

Pure and side-effect free. Position sizing refuses to pass a trade it cannot
verify: without an account equity and a risk budget the result is not "passed"
(spec ch. 16.4 — a candidate must clear risk first). Nothing here liquidates a
position; drawdown returns a *policy* action, not an order.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from ..domain.risk import (
    DRAWDOWN_ACTIONS,
    ExitSignal,
    Greeks,
    PositionLeg,
    TradeRisk,
)

__all__ = ["aggregate_greeks", "assess_trade", "drawdown_action", "exit_signals"]


def assess_trade(
    *,
    max_loss_per_contract: float,
    account_equity: float | None = None,
    max_account_risk_pct: float | None = None,
) -> TradeRisk:
    """Size a trade against the account risk budget (spec 16.4 / 5.1)."""
    if not math.isfinite(max_loss_per_contract) or max_loss_per_contract <= 0:
        return TradeRisk(
            max_loss_per_contract=max_loss_per_contract,
            passed=False,
            reasons=("max_loss_per_contract must be positive",),
        )
    if account_equity is None or account_equity <= 0:
        return TradeRisk(
            max_loss_per_contract=max_loss_per_contract,
            passed=False,
            reasons=("account equity unavailable",),
        )
    if max_account_risk_pct is None:
        return TradeRisk(
            max_loss_per_contract=max_loss_per_contract,
            passed=False,
            reasons=("max_account_risk_pct undetermined",),
        )

    allowed_risk = account_equity * max_account_risk_pct
    contracts = math.floor(allowed_risk / max_loss_per_contract)
    risk_pct = max_loss_per_contract / account_equity
    if contracts < 1:
        return TradeRisk(
            max_loss_per_contract=max_loss_per_contract,
            allowed_risk=allowed_risk,
            recommended_contracts=0,
            risk_pct_of_equity=risk_pct,
            passed=False,
            reasons=("allowed risk cannot fund a single contract",),
        )
    return TradeRisk(
        max_loss_per_contract=max_loss_per_contract,
        allowed_risk=allowed_risk,
        recommended_contracts=contracts,
        risk_pct_of_equity=risk_pct,
        passed=True,
    )


def aggregate_greeks(legs: Sequence[PositionLeg]) -> Greeks:
    """Sum signed, multiplier-scaled Greeks across position legs."""
    delta = gamma = theta = vega = rho = 0.0
    for leg in legs:
        scale = leg.quantity * leg.multiplier
        delta += leg.greeks.delta * scale
        gamma += leg.greeks.gamma * scale
        theta += leg.greeks.theta * scale
        vega += leg.greeks.vega * scale
        rho += leg.greeks.rho * scale
    return Greeks(delta=delta, gamma=gamma, theta=theta, vega=vega, rho=rho)


def exit_signals(
    *,
    cost_to_close: float | None,
    net_credit: float | None,
    dte: int | None,
    take_profit_pct: float | None = None,
    stop_review_multiple: float | None = None,
    time_exit_dte: int | None = None,
) -> list[ExitSignal]:
    """Return exit signals for a credit position; unknowns yield no signal."""
    signals: list[ExitSignal] = []
    if (
        cost_to_close is not None
        and net_credit is not None
        and net_credit > 0
        and take_profit_pct is not None
        and cost_to_close <= net_credit * take_profit_pct
    ):
        signals.append(
            ExitSignal("take_profit", f"cost {cost_to_close} <= {take_profit_pct} x credit")
        )
    if (
        cost_to_close is not None
        and net_credit is not None
        and net_credit > 0
        and stop_review_multiple is not None
        and cost_to_close >= net_credit * stop_review_multiple
    ):
        signals.append(
            ExitSignal("stop_review", f"cost {cost_to_close} >= {stop_review_multiple} x credit")
        )
    if dte is not None and time_exit_dte is not None and dte <= time_exit_dte:
        signals.append(ExitSignal("time_exit", f"dte {dte} <= {time_exit_dte}"))
    return signals


def drawdown_action(drawdown_pct: float, *, threshold_pct: float, action: str) -> str:
    """Return the drawdown response *policy* once the threshold is breached."""
    if action not in DRAWDOWN_ACTIONS:
        raise ValueError(f"unknown drawdown action: {action!r}")
    if drawdown_pct < threshold_pct:
        return "none"
    return action
