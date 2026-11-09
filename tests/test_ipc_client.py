from __future__ import annotations

import socket
from pathlib import Path

import pytest

from mooc.ipc import protocol
from mooc.ipc.client import IpcClient


class _FakeSock:
    def __init__(self, *args, **kwargs) -> None:
        self.timeout = None
        self._response = protocol.encode(protocol.OptionExpirationsResult(dates=[]))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def settimeout(self, value):
        self.timeout = value

    def connect(self, _path):
        pass

    def sendall(self, _data):
        pass

    def recv(self, size):
        chunk, self._response = self._response[:size], self._response[size:]
        return chunk


@pytest.fixture()
def sock_path(tmp_path: Path) -> Path:
    path = tmp_path / "mooc.sock"
    path.write_text("")
    return path


def test_request_uses_default_timeout(sock_path, monkeypatch):
    created = []
    monkeypatch.setattr(
        socket, "socket", lambda *a, **k: created.append(_FakeSock()) or created[-1]
    )
    IpcClient(sock_path, timeout=15.0).request(protocol.GetWatchlistGroups())
    assert created[-1].timeout == 15.0


def test_request_timeout_override(sock_path, monkeypatch):
    created = []
    monkeypatch.setattr(
        socket, "socket", lambda *a, **k: created.append(_FakeSock()) or created[-1]
    )
    IpcClient(sock_path, timeout=15.0).request(protocol.GetWatchlistGroups(), timeout=45.0)
    assert created[-1].timeout == 45.0
