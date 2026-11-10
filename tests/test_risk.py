from __future__ import annotations

import pytest

from mooc.domain.risk import Greeks, PositionLeg
from mooc.services import risk


def test_assess_trade_sizes_down():
    result = risk.assess_trade(
        max_loss_per_contract=400.0, account_equity=10000.0, max_account_risk_pct=0.25
    )
    assert result.passed is True
    assert result.allowed_risk == 2500.0
    assert result.recommended_contracts == 6  # floor(2500 / 400)
    assert result.risk_pct_of_equity == pytest.approx(0.04)


def test_assess_trade_requires_equity_and_budget():
    no_equity = risk.assess_trade(max_loss_per_contract=400.0)
    assert no_equity.passed is False
    assert no_equity.recommended_contracts is None
    assert no_equity.reasons == ("account equity unavailable",)

    no_budget = risk.assess_trade(
        max_loss_per_contract=400.0, account_equity=10000.0, max_account_risk_pct=None
    )
    assert no_budget.reasons == ("max_account_risk_pct undetermined",)


def test_assess_trade_cannot_fund_one_contract():
    result = risk.assess_trade(
        max_loss_per_contract=500.0, account_equity=1000.0, max_account_risk_pct=0.25
    )
    assert result.passed is False
    assert result.recommended_contracts == 0


def test_assess_trade_rejects_nonpositive_loss():
    result = risk.assess_trade(
        max_loss_per_contract=0.0, account_equity=10000.0, max_account_risk_pct=0.25
    )
    assert result.passed is False
    assert result.reasons == ("max_loss_per_contract must be positive",)


def test_aggregate_greeks_signed_and_scaled():
    legs = [
        PositionLeg(greeks=Greeks(delta=0.30, theta=-0.05), quantity=-1),  # short
        PositionLeg(greeks=Greeks(delta=0.20, theta=-0.03), quantity=1),  # long
    ]
    total = risk.aggregate_greeks(legs)
    assert total.delta == pytest.approx((0.20 - 0.30) * 100)
    assert total.theta == pytest.approx((-0.03 + 0.05) * 100)


def test_exit_signals():
    signals = risk.exit_signals(
        cost_to_close=0.20,
        net_credit=0.50,
        dte=40,
        take_profit_pct=0.50,
        stop_review_multiple=2.0,
        time_exit_dte=21,
    )
    assert [s.kind for s in signals] == ["take_profit"]  # 0.20 <= 0.25

    stop = risk.exit_signals(cost_to_close=1.10, net_credit=0.50, dte=40, stop_review_multiple=2.0)
    assert [s.kind for s in stop] == ["stop_review"]

    time_exit = risk.exit_signals(cost_to_close=0.40, net_credit=0.50, dte=10, time_exit_dte=21)
    assert [s.kind for s in time_exit] == ["time_exit"]

    assert risk.exit_signals(cost_to_close=None, net_credit=0.5, dte=40) == []


def test_drawdown_action_is_policy_not_liquidation():
    assert risk.drawdown_action(1.0, threshold_pct=3.0, action="alert_only") == "none"
    assert risk.drawdown_action(3.0, threshold_pct=3.0, action="alert_only") == "alert_only"
    assert risk.drawdown_action(5.0, threshold_pct=3.0, action="stop_new") == "stop_new"
    with pytest.raises(ValueError):
        risk.drawdown_action(5.0, threshold_pct=3.0, action="liquidate")
