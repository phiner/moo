from __future__ import annotations

from pathlib import Path

import pytest

from mooc.domain.rules import UNSET
from mooc.opend.errors import MoocError
from mooc.services import rules

EXAMPLES = Path(__file__).resolve().parents[1] / "rules"


def test_load_example_rule_tristate():
    loaded = rules.load_rules(EXAMPLES)
    assert [rule.name for rule in loaded] == ["bull_put_credit_spread"]
    rule = loaded[0]
    assert rule.enabled is True
    assert rule.allowed_regimes == ("bullish", "strong_bullish")
    # present-but-null -> undetermined (None), not UNSET
    assert rule.iv_rank_min is None
    assert rule.iv_percentile_min is None
    # concrete values preserved
    assert rule.min_dte == 30
    assert rule.max_dte == 45
    assert rule.delta_min == 0.15
    assert rule.max_account_risk_pct == 0.25
    # absent section -> UNSET
    assert rule.take_profit_pct == 0.5
    assert rule.undetermined() == ("iv_rank_min", "iv_rank_max", "iv_percentile_min")


def test_parse_rule_missing_name_raises():
    with pytest.raises(MoocError):
        rules.parse_rule({"strategy": {"enabled": True}})


def test_parse_rule_bad_number_raises():
    with pytest.raises(MoocError):
        rules.parse_rule({"strategy": {"name": "x", "expiration": {"min_dte": "soon"}}})


def test_absent_vs_null(tmp_path: Path):
    cfg = tmp_path / "r.yaml"
    cfg.write_text(
        "strategy:\n  name: x\n  volatility:\n    iv_rank_min: null\n"
        "  expiration:\n    min_dte: 20\n"
    )
    rule = rules.load_rules(cfg)[0]
    assert rule.iv_rank_min is None  # present, null
    assert rule.iv_rank_max is UNSET  # absent
    assert rule.min_dte == 20
    assert rule.max_dte is UNSET


def test_missing_path_raises(tmp_path: Path):
    with pytest.raises(MoocError):
        rules.load_rules(tmp_path / "does-not-exist")
