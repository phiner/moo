from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from mooc.config import AppConfig
from mooc.domain.decision import TradeStatus
from mooc.domain.rules import StrategyRule
from mooc.services.analyze import analyze_symbol

NOW = datetime(2026, 11, 9, 20, 0, tzinfo=UTC)


def _bars_frame(count: int = 60) -> pd.DataFrame:
    start = datetime(2026, 1, 1)
    return pd.DataFrame(
        [
            {
                "time_key": (start + timedelta(days=index)).strftime("%Y-%m-%d"),
                "open": 100.0 + index,
                "close": 100.0 + index,
                "high": 101.0 + index,
                "low": 99.0 + index,
                "volume": 1000,
            }
            for index in range(count)
        ]
    )


class _Ctx:
    def __init__(self) -> None:
        self.kline_calls = 0

    def request_history_kline(self, code, **kwargs):
        self.kline_calls += 1
        return 0, _bars_frame(), None

    def get_option_underlying_his_volatility(self, code, **kwargs):
        frame = pd.DataFrame(
            [
                {"time": "2026-11-07", "iv": 30.0, "hv": 22.0, "underlying_price": 150.0},
                {"time": "2026-11-08", "iv": 55.0, "hv": 22.0, "underlying_price": 160.0},
            ]
        )
        return 0, frame, None

    def get_market_snapshot(self, codes):
        return 0, pd.DataFrame(
            [
                {
                    "code": "US.AAPL",
                    "update_time": NOW.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                    "last_price": 160.0,
                    "bid_price": 159.9,
                    "ask_price": 160.1,
                    "volume": 5000,
                }
            ]
        )

    def get_earnings_calendar(self, market, begin_date=None, end_date=None, **kwargs):
        return 0, pd.DataFrame()


class _Client:
    def __init__(self) -> None:
        self.quote_ctx = _Ctx()


def _config() -> AppConfig:
    return AppConfig()


def test_analyze_reports_regime_and_rejects_on_missing_contract_inputs():
    rule = StrategyRule(
        name="bull_put_credit_spread",
        allowed_regimes=("bullish", "strong_bullish"),
        min_dte=30,
        max_dte=45,
        delta_min=0.15,
        delta_max=0.25,
    )
    output = analyze_symbol(_Client(), "US.AAPL", rules=[rule], config=_config(), now=NOW)
    assert output.symbol == "US.AAPL"
    assert output.market_regime == "strong_bullish"
    assert output.volatility_regime == "high"  # iv_rank = 100 over the tiny series
    assert output.event_risk == "low"
    assert output.trade_status is TradeStatus.REJECTED
    assert any("dte unavailable" in reason for reason in output.rejection_reasons)
    assert any("delta unavailable" in reason for reason in output.rejection_reasons)
    payload = output.to_dict()
    assert payload["strategy"]["type"] == "bull_put_credit_spread"


def test_analyze_without_rules_is_no_trade():
    output = analyze_symbol(_Client(), "US.AAPL", rules=[], config=_config(), now=NOW)
    assert output.trade_status is TradeStatus.REJECTED
    assert output.rejection_reasons == ["no enabled strategy rules configured"]
    assert output.market_regime == "strong_bullish"


def test_analyze_null_rule_field_blocks():
    rule = StrategyRule(name="bull_put_credit_spread", iv_rank_min=None)
    output = analyze_symbol(_Client(), "US.AAPL", rules=[rule], config=_config(), now=NOW)
    assert output.trade_status is TradeStatus.REJECTED
    assert "undetermined (null): iv_rank_min" in output.rejection_reasons
