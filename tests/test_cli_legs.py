from __future__ import annotations

import pytest

from mooc.cli import _parse_legs
from mooc.opend.errors import MoocError


def test_parse_legs_ok():
    legs = _parse_legs('[{"code":"US.AAPL261118C270000","action":"BUY","quantity":2}]')
    assert legs[0].code == "US.AAPL261118C270000"
    assert legs[0].quantity == 2.0
    assert legs[0].action.value == "BUY"


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "{}",
        "[]",
        '[{"action":"BUY"}]',
        '[{"code":"X","action":"HOLD"}]',
        '[{"code":"X","quantity":0}]',
        '[{"code":"X","quantity":-1}]',
        '[{"code":"X","quantity":NaN}]',
    ],
)
def test_parse_legs_invalid(raw):
    with pytest.raises(MoocError):
        _parse_legs(raw)
