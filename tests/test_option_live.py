from __future__ import annotations

import pytest

from mooc.domain.options import LegAction, OptionLeg
from mooc.opend import option
from mooc.opend.client import OpendClient
from mooc.opend.errors import OpendUnavailable

pytestmark = pytest.mark.live


@pytest.fixture()
def client():
    client = OpendClient()
    try:
        client.connect()
    except OpendUnavailable:
        pytest.skip("OpenD not reachable")
    yield client
    client.close()


def test_expirations_and_chain(client):
    dates = option.list_expirations(client, "US.AAPL")
    assert dates, "expected at least one expiration"
    chain = option.get_chain(client, "US.AAPL", start=dates[0], end=dates[0])
    assert chain.contracts, "expected contracts for the first expiry"


def test_combo_analysis_returns_bid_ask(client):
    dates = option.list_expirations(client, "US.AAPL")
    chain = option.get_chain(client, "US.AAPL", start=dates[1], end=dates[1])
    calls = [c for c in chain.contracts if c.option_type.value == "CALL"][:2]
    if len(calls) < 2:
        pytest.skip("not enough calls for a spread")
    legs = [
        OptionLeg(code=calls[0].code, action=LegAction.BUY, quantity=1.0),
        OptionLeg(code=calls[1].code, action=LegAction.SELL, quantity=1.0),
    ]
    analysis = option.combo_analysis(client, legs)
    assert analysis.ask1 >= analysis.bid1
