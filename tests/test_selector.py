from __future__ import annotations

from datetime import date

import pytest

from mooc.domain.options import OptionType
from mooc.services import selector

TODAY = date(2026, 11, 9)
EXPIRY = date(2026, 12, 18)


def _c(strike: float, option_type: OptionType, bid: float, ask: float, delta: float):
    return selector.ContractQuote(
        code=f"X{strike}{option_type.value}",
        expiry=EXPIRY,
        strike=strike,
        option_type=option_type,
        bid=bid,
        ask=ask,
        delta=delta,
    )


def _puts():
    # Put deltas are negative; the selector matches on magnitude.
    return [
        _c(95, OptionType.PUT, 1.00, 1.10, -0.15),
        _c(100, OptionType.PUT, 2.00, 2.10, -0.25),
        _c(105, OptionType.PUT, 3.00, 3.10, -0.45),
    ]


def test_shape_for_known_and_unknown():
    assert selector.shape_for("bull_put_credit_spread") == (OptionType.PUT, True, True)
    assert selector.shape_for("bear_call_credit_spread") == (OptionType.CALL, False, True)
    assert selector.shape_for("cash_secured_put") is None


def test_select_bull_put_credit_spread():
    outcome = selector.select_spread(
        _puts(),
        today=TODAY,
        option_type=OptionType.PUT,
        short_is_higher=True,
        is_credit=True,
        min_dte=30,
        max_dte=45,
        delta_min=0.15,
        delta_max=0.25,
        min_width=5,
        max_width=5,
    )
    selection = outcome.selection
    assert selection is not None
    assert selection.short.strike == 100.0
    assert selection.long.strike == 95.0
    assert selection.width == 5.0
    assert selection.net_per_share == pytest.approx(0.90)  # short bid 2.00 - long ask 1.10
    assert selection.dte == (EXPIRY - TODAY).days
    assert selection.delta == 0.25


def test_no_expiry_within_dte_bounds():
    outcome = selector.select_spread(
        _puts(),
        today=TODAY,
        option_type=OptionType.PUT,
        short_is_higher=True,
        is_credit=True,
        min_dte=1,
        max_dte=5,
        delta_min=0.15,
        delta_max=0.25,
        min_width=5,
        max_width=5,
    )
    assert outcome.selection is None
    assert outcome.reasons == ("no expiry within DTE bounds",)


def test_undetermined_bounds_are_explicit():
    outcome = selector.select_spread(
        _puts(),
        today=TODAY,
        option_type=OptionType.PUT,
        short_is_higher=True,
        is_credit=True,
        min_dte=30,
        max_dte=45,
        delta_min=None,
        delta_max=None,
        min_width=5,
        max_width=5,
    )
    assert outcome.selection is None
    assert outcome.reasons == ("delta bounds undetermined",)


def test_empty_contracts():
    outcome = selector.select_spread(
        [],
        today=TODAY,
        option_type=OptionType.PUT,
        short_is_higher=True,
        is_credit=True,
        min_dte=30,
        max_dte=45,
        delta_min=0.15,
        delta_max=0.25,
        min_width=5,
        max_width=5,
    )
    assert outcome.reasons == ("no contracts available",)
