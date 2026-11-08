from __future__ import annotations

import pytest

from mooc.opend import trade
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


def test_accounts_and_positions(client):
    try:
        accounts = trade.list_accounts(client, "SIMULATE")
        positions = trade.list_positions(client, "SIMULATE")
    except OpendUnavailable:
        pytest.skip("trade context unavailable")
    assert isinstance(accounts, list)
    assert isinstance(positions, list)
