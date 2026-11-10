from __future__ import annotations

import pytest

from mooc.domain.strategy import CostModel, StrategyType
from mooc.services import pricing


def test_bull_put_credit_spread_atm_numbers():
    result = pricing.bull_put_credit_spread(
        short_strike=100, long_strike=95, short_bid=2.00, long_ask=1.00
    )
    assert result.strategy is StrategyType.BULL_PUT_CREDIT_SPREAD
    assert result.is_credit is True
    assert result.net_premium == 100.0  # (2.00 - 1.00) * 100
    assert result.max_profit == 100.0
    assert result.max_loss == 400.0  # (5 - 1.00) * 100
    assert result.breakeven == [99.0]


def test_bear_call_credit_spread_numbers():
    result = pricing.bear_call_credit_spread(
        short_strike=100, long_strike=105, short_bid=2.00, long_ask=1.00
    )
    assert result.net_premium == 100.0
    assert result.max_loss == 400.0
    assert result.breakeven == [101.0]


def test_cash_secured_put_numbers():
    result = pricing.cash_secured_put(strike=100, put_bid=3.00)
    assert result.net_premium == 300.0
    assert result.cash_required == 10000.0
    assert result.breakeven == [97.0]
    assert result.max_loss == 9700.0  # (100 - 3) * 100


def test_covered_call_with_and_without_stock_cost():
    with_cost = pricing.covered_call(strike=105, call_bid=2.00, stock_cost=100.0)
    assert with_cost.net_premium == 200.0
    assert with_cost.max_profit == 700.0  # (105 + 2 - 100) * 100
    assert with_cost.max_loss == 9800.0  # (100 - 2) * 100
    assert with_cost.breakeven == [98.0]

    without = pricing.covered_call(strike=105, call_bid=2.00)
    assert without.net_premium == 200.0
    assert without.max_profit is None
    assert without.breakeven == []


def test_debit_spreads_are_debits():
    bull_call = pricing.bull_call_debit_spread(
        long_strike=100, short_strike=105, long_ask=3.00, short_bid=1.00
    )
    assert bull_call.is_credit is False
    assert bull_call.net_premium == -200.0
    assert bull_call.max_loss == 200.0
    assert bull_call.max_profit == 300.0  # (5 - 2) * 100
    assert bull_call.breakeven == [102.0]

    bear_put = pricing.bear_put_debit_spread(
        long_strike=105, short_strike=100, long_ask=3.00, short_bid=1.00
    )
    assert bear_put.net_premium == -200.0
    assert bear_put.max_profit == 300.0
    assert bear_put.breakeven == [103.0]


def test_conversion_locked_value():
    result = pricing.conversion(strike=100, stock_ask=100.0, put_ask=2.0, call_bid=3.0)
    assert result.net_premium == -9900.0  # (100 + 2 - 3) * 100
    assert result.max_profit == 100.0  # 10000 - 9900
    assert result.max_loss == 100.0


def test_costs_worsen_economics():
    cost = CostModel(per_contract_fee=0.65, slippage_per_share=0.05)
    result = pricing.bull_put_credit_spread(
        short_strike=100,
        long_strike=95,
        short_bid=2.00,
        long_ask=1.00,
        contracts=2,
        cost=cost,
    )
    # sell 1.95, buy 1.05 -> net 0.90/share * 100 * 2 = 180; fees 0.65*2*2 = 2.60
    assert result.net_premium == pytest.approx(180.0 - 2.60)
    assert result.max_loss == pytest.approx(1000.0 - (180.0 - 2.60))


def test_itm_bull_put_still_bounded():
    # Deep ITM credit spread: credit exceeds intrinsic-at-zero? max_loss must floor at width - credit.
    result = pricing.bull_put_credit_spread(
        short_strike=100, long_strike=90, short_bid=12.00, long_ask=3.00
    )
    assert result.net_premium == 900.0
    assert result.max_loss == 1000.0 - 900.0
    assert result.breakeven == [91.0]


def test_invalid_strikes_raise():
    with pytest.raises(ValueError):
        pricing.bull_put_credit_spread(
            short_strike=95, long_strike=100, short_bid=2.0, long_ask=1.0
        )
    with pytest.raises(ValueError):
        pricing.bull_call_debit_spread(
            long_strike=105, short_strike=100, long_ask=3.0, short_bid=1.0
        )
