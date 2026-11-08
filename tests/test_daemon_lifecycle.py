from __future__ import annotations

import asyncio
import contextlib
import os

import pytest

from mooc.daemon.lifecycle import (
    acquire_startup_lock,
    daemon_paths,
    is_running,
    socket_is_live,
)
from mooc.daemon.server import DaemonServer
from mooc.ipc import protocol
from mooc.opend.client import OpendClient
from mooc.opend.errors import MoocError


def test_acquire_lock_is_exclusive(tmp_path):
    paths = daemon_paths(tmp_path)
    fd = acquire_startup_lock(paths)
    try:
        with pytest.raises(MoocError):
            acquire_startup_lock(paths)
    finally:
        os.close(fd)
    fd2 = acquire_startup_lock(paths)
    os.close(fd2)


def test_socket_is_live_false_when_missing(tmp_path):
    assert socket_is_live(tmp_path / "nope.sock") is False


def test_server_roundtrip_errors_and_cleanup(tmp_path):
    paths = daemon_paths(tmp_path)
    server = DaemonServer(paths, OpendClient())  # client intentionally unconnected

    async def scenario() -> None:
        task = asyncio.create_task(server.serve_forever())
        for _ in range(100):
            if paths.socket.exists():
                break
            await asyncio.sleep(0.02)
        assert paths.socket.exists()
        assert is_running(paths)

        reader, writer = await asyncio.open_unix_connection(str(paths.socket))

        writer.write(b"{not json}\n")
        await writer.drain()
        assert protocol.decode_response(await reader.readline()).kind == "Error"

        writer.write(protocol.encode(protocol.GetOptionExpirations(underlying="US.AAPL")))
        await writer.drain()
        assert protocol.decode_response(await reader.readline()).kind == "Error"

        writer.close()

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert not paths.socket.exists()
    assert not paths.pid.exists()
