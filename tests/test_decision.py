from __future__ import annotations

import pytest

from mooc.domain.decision import DecisionOutput, TradeStatus, can_transition, transition
from mooc.domain.rules import StrategyRule
from mooc.opend.errors import MoocError
from mooc.services import decision

TS = "2026-11-09T20:00:00+00:00"


def _rule(**overrides) -> StrategyRule:
    base = {
        "name": "bull_put_credit_spread",
        "allowed_regimes": ("bullish", "strong_bullish"),
        "min_dte": 30,
        "max_dte": 45,
        "delta_min": 0.15,
        "delta_max": 0.25,
    }
    base.update(overrides)
    return StrategyRule(**base)


def test_null_fields_block_with_reasons():
    rule = _rule(iv_rank_min=None, iv_rank_max=None)
    reasons = decision.evaluate_strategy(rule, decision.StrategyInputs())
    assert reasons == ["undetermined (null): iv_rank_min", "undetermined (null): iv_rank_max"]


def test_concrete_values_pass_and_fail():
    inputs = decision.StrategyInputs(market_regime="bullish", dte=40, delta=0.20, iv_rank=50.0)
    assert decision.evaluate_strategy(_rule(), inputs) == []

    bad = decision.StrategyInputs(market_regime="bearish", dte=10, delta=0.60)
    reasons = decision.evaluate_strategy(_rule(), bad)
    assert any("not in" in reason for reason in reasons)
    assert any("dte 10 below min 30" in reason for reason in reasons)
    assert any("delta 0.6 above max 0.25" in reason for reason in reasons)


def test_missing_input_is_a_reason():
    reasons = decision.evaluate_strategy(_rule(), decision.StrategyInputs(market_regime="bullish"))
    assert "dte unavailable" in reasons


def test_build_output_candidate_and_no_trade():
    ok = decision.build_output(
        _rule(),
        decision.StrategyInputs(market_regime="bullish", dte=40, delta=0.2),
        symbol="US.AAPL",
        timestamp=TS,
    )
    assert ok.trade_status is TradeStatus.CANDIDATE
    assert ok.recommended_action == "consider_bull_put_credit_spread"
    assert ok.rejection_reasons == []

    blocked = decision.build_output(
        _rule(iv_rank_min=None),
        decision.StrategyInputs(market_regime="bullish", dte=40, delta=0.2),
        symbol="US.AAPL",
        timestamp=TS,
    )
    assert blocked.trade_status is TradeStatus.REJECTED
    assert blocked.recommended_action == "no_trade"
    assert blocked.missing_data == ["iv_rank_min"]
    payload = blocked.to_dict()
    assert payload["trade_status"] == "REJECTED"
    assert payload["strategy"]["type"] == "bull_put_credit_spread"


def test_unknown_strategy_name_rejected():
    output = decision.build_output(
        StrategyRule(name="nonsense"),
        decision.StrategyInputs(),
        symbol="US.AAPL",
        timestamp=TS,
    )
    assert output.trade_status is TradeStatus.REJECTED
    assert output.rejection_reasons == ["unknown strategy 'nonsense'"]


def test_status_machine_legal_and_illegal():
    assert can_transition(TradeStatus.SCANNED, TradeStatus.ANALYZED)
    assert can_transition(TradeStatus.CANDIDATE, TradeStatus.REJECTED)
    assert transition(TradeStatus.READY, TradeStatus.APPROVED) is TradeStatus.APPROVED
    assert not can_transition(TradeStatus.CLOSED, TradeStatus.OPEN)
    with pytest.raises(MoocError):
        transition(TradeStatus.SCANNED, TradeStatus.OPEN)


def test_decision_output_defaults_are_none_not_invented():
    output = DecisionOutput(
        symbol="US.AAPL",
        analysis_timestamp=TS,
        data_quality="valid",
        recommended_action="no_trade",
        trade_status=TradeStatus.REJECTED,
    )
    payload = output.to_dict()
    assert payload["strategy"] == {}
    assert payload["missing_data"] == []
