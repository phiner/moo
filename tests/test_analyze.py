from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from mooc.config import AppConfig
from mooc.domain.decision import TradeStatus
from mooc.domain.rules import StrategyRule
from mooc.services.analyze import analyze_symbol

NOW = datetime(2026, 11, 9, 20, 0, tzinfo=UTC)
EXPIRY = "2026-12-18"
EXPIRY_CODE = "261218"


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
    def __init__(self, *, with_chain: bool = False) -> None:
        self._with_chain = with_chain
        self._bids = {"US.AAPL261218P95000": 1.00, "US.AAPL261218P100000": 2.00}
        self._deltas = {"US.AAPL261218P95000": 0.15, "US.AAPL261218P100000": 0.25}

    def request_history_kline(self, code, **kwargs):
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
        rows = []
        for code in codes:
            if code == "US.AAPL":
                rows.append(
                    {
                        "code": code,
                        "update_time": NOW.strftime("%Y-%m-%d %H:%M:%S"),
                        "last_price": 160.0,
                        "bid_price": 159.9,
                        "ask_price": 160.1,
                        "volume": 5000,
                    }
                )
            elif code in self._bids:
                rows.append(
                    {
                        "code": code,
                        "stock_owner": "US.AAPL",
                        "update_time": NOW.strftime("%Y-%m-%d %H:%M:%S"),
                        "last_price": self._bids[code],
                        "bid_price": self._bids[code],
                        "ask_price": self._bids[code] + 0.10,
                        "volume": 100,
                        "option_delta": self._deltas[code],
                        "option_implied_volatility": 0.3,
                        "option_open_interest": 500,
                    }
                )
        return 0, pd.DataFrame(rows)

    def get_earnings_calendar(self, market, begin_date=None, end_date=None, **kwargs):
        return 0, pd.DataFrame()

    def get_option_chain(self, code, **kwargs):
        if not self._with_chain:
            return 0, pd.DataFrame(
                columns=[
                    "code",
                    "stock_owner",
                    "strike_time",
                    "strike_price",
                    "option_type",
                    "lot_size",
                ]
            )
        rows = [
            {
                "code": f"US.AAPL{EXPIRY_CODE}P95000",
                "stock_owner": "US.AAPL",
                "strike_time": EXPIRY,
                "strike_price": 95.0,
                "option_type": "PUT",
                "lot_size": 100,
            },
            {
                "code": f"US.AAPL{EXPIRY_CODE}P100000",
                "stock_owner": "US.AAPL",
                "strike_time": EXPIRY,
                "strike_price": 100.0,
                "option_type": "PUT",
                "lot_size": 100,
            },
        ]
        return 0, pd.DataFrame(rows)


class _Client:
    def __init__(self, *, with_chain: bool = False) -> None:
        self.quote_ctx = _Ctx(with_chain=with_chain)


def _rule(**overrides) -> StrategyRule:
    base = {
        "name": "bull_put_credit_spread",
        "allowed_regimes": ("bullish", "strong_bullish"),
        "min_dte": 30,
        "max_dte": 45,
        "delta_min": 0.15,
        "delta_max": 0.25,
        "min_width": 5,
        "max_width": 5,
    }
    base.update(overrides)
    return StrategyRule(**base)


def test_analyze_reports_regime_and_rejects_on_missing_contract_inputs():
    output = analyze_symbol(_Client(), "US.AAPL", rules=[_rule()], config=AppConfig(), now=NOW)
    assert output.market_regime == "strong_bullish"
    assert output.volatility_regime == "high"
    assert output.event_risk == "low"
    assert output.trade_status is TradeStatus.REJECTED
    assert any("dte unavailable" in reason for reason in output.rejection_reasons)


def test_analyze_selects_spread_and_fills_strategy_block():
    output = analyze_symbol(
        _Client(with_chain=True), "US.AAPL", rules=[_rule()], config=AppConfig(), now=NOW
    )
    assert output.trade_status is TradeStatus.CANDIDATE
    assert output.recommended_action == "consider_bull_put_credit_spread"
    strategy = output.strategy
    assert strategy["expiration"] == EXPIRY
    assert strategy["short_strike"] == 100.0
    assert strategy["long_strike"] == 95.0
    # short bid 2.00 - long ask 1.10 = 0.90/share -> 90.0 per contract
    assert strategy["net_credit"] == pytest.approx(90.0)
    assert strategy["max_loss"] == pytest.approx(410.0)


def test_analyze_without_rules_is_no_trade():
    output = analyze_symbol(_Client(), "US.AAPL", rules=[], config=AppConfig(), now=NOW)
    assert output.trade_status is TradeStatus.REJECTED
    assert output.rejection_reasons == ["no enabled strategy rules configured"]


def test_analyze_null_rule_field_blocks():
    output = analyze_symbol(
        _Client(with_chain=True),
        "US.AAPL",
        rules=[_rule(iv_rank_min=None)],
        config=AppConfig(),
        now=NOW,
    )
    assert output.trade_status is TradeStatus.REJECTED
    assert "undetermined (null): iv_rank_min" in output.rejection_reasons
