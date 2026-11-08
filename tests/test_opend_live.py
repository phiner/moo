from __future__ import annotations

import pytest

from mooc.opend.client import OpendClient
from mooc.opend.errors import OpendUnavailable

pytestmark = pytest.mark.live


def test_opend_health_roundtrip():
    client = OpendClient()
    try:
        client.connect()
    except OpendUnavailable:
        pytest.skip("OpenD not reachable")
    try:
        health = client.health()
    finally:
        client.close()
    assert health.server_ver and health.server_ver != "?"
