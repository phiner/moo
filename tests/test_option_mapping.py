from __future__ import annotations

import pandas as pd
import pytest

from mooc.domain.options import LegAction, OptionLeg, OptionType
from mooc.opend import option
from mooc.opend.errors import OpendRejected


class _FakeCtx:
    def __init__(self, **frames: pd.DataFrame) -> None:
        self._frames = frames

    def get_option_expiration_date(self, code):
        return 0, self._frames["expiration"]

    def get_option_chain(self, code, **kwargs):
        return 0, self._frames["chain"]

    def get_option_quote(self, legs):
        return 0, self._frames["quote"]

    def get_option_strategy_analysis(self, legs):
        return 0, self._frames["analysis"]


class _FakeClient:
    def __init__(self, ctx: _FakeCtx) -> None:
        self._ctx = ctx

    @property
    def quote_ctx(self):
        return self._ctx


def _client(**frames: pd.DataFrame) -> _FakeClient:
    return _FakeClient(_FakeCtx(**frames))


def test_list_expirations_normalizes_to_iso_date():
    df = pd.DataFrame({"strike_time": ["2026-11-18 00:00:00", "2026-12-19"]})
    assert option.list_expirations(_client(expiration=df), "US.AAPL") == [
        "2026-11-18",
        "2026-12-19",
    ]


def test_get_chain_maps_fields():
    chain = pd.DataFrame(
        [
            {
                "code": "US.AAPL261118C270000",
                "stock_owner": "US.AAPL",
                "strike_time": "2026-11-18",
                "strike_price": 270.0,
                "option_type": "CALL",
                "lot_size": 100,
            }
        ]
    )
    result = option.get_chain(_client(chain=chain), "US.AAPL")
    contract = result.contracts[0]
    assert contract.option_type is OptionType.CALL
    assert contract.strike == 270.0
    assert contract.multiplier == 100
    assert contract.expiry.isoformat() == "2026-11-18"


def test_get_quote_treats_missing_markers_as_none():
    quote = pd.DataFrame(
        [
            {
                "price": "74.1",
                "implied_volatility": "N/A",
                "delta": 0.98,
                "gamma": 0.001,
                "theta": -0.1,
                "vega": 0.02,
                "rho": 0.07,
                "open_interest": "25",
                "volume": "8",
            }
        ]
    )
    legs = [OptionLeg(code="US.AAPL261118C270000", action=LegAction.BUY, quantity=1.0)]
    result = option.get_quote(_client(quote=quote), legs)[0]
    assert result.last == 74.1
    assert result.iv is None
    assert result.oi == 25


def test_combo_analysis_parses_fields():
    analysis = pd.DataFrame(
        [
            {
                "code": "AAPL261118C270/280",
                "name": "AAPL Vertical Spread",
                "option_strategy": "SPREAD",
                "bid1": 6.4,
                "ask1": 13.4,
                "max_profit": 10.0,
                "max_loss": -990.0,
                "breakeven_points": "[279.9]",
                "prob_of_profit": 99.9,
                "delta": 0.007,
                "theta": 0.018,
            }
        ]
    )
    legs = [OptionLeg(code="US.AAPL261118C270000", action=LegAction.BUY, quantity=1.0)]
    result = option.combo_analysis(_client(analysis=analysis), legs)
    assert (result.bid1, result.ask1) == (6.4, 13.4)
    assert result.breakeven == [279.9]
    assert result.strategy == "SPREAD"


def test_combo_analysis_empty_result_raises():
    legs = [OptionLeg(code="US.AAPL261118C270000", action=LegAction.BUY, quantity=1.0)]
    with pytest.raises(OpendRejected):
        option.combo_analysis(_client(analysis=pd.DataFrame()), legs)
