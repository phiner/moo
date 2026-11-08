"""Async Unix-socket server: decodes typed IPC, dispatches, encodes responses."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal

from ..ipc import protocol
from ..opend.client import OpendClient
from ..services.option_data import OptionDataService
from .lifecycle import (
    DaemonPaths,
    acquire_startup_lock,
    socket_is_live,
)

logger = logging.getLogger(__name__)


class DaemonServer:
    def __init__(self, paths: DaemonPaths, client: OpendClient) -> None:
        self._paths = paths
        self._client = client
        self._service = OptionDataService(client)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        logger.info("ipc client connected")
        try:
            while True:
                try:
                    line = await reader.readline()
                except ValueError as exc:  # frame larger than the reader limit
                    await self._send(
                        writer, protocol.ErrorResult(message=f"frame too large: {exc}")
                    )
                    break
                if not line:
                    break
                try:
                    request = protocol.decode_request(line)
                except Exception as exc:  # noqa: BLE001 - boundary: never kill the loop
                    await self._send(writer, protocol.ErrorResult(message=f"bad request: {exc}"))
                    continue
                # SDK calls are blocking; keep the event loop responsive.
                response = await asyncio.to_thread(self._service.dispatch, request)
                await self._send(writer, response)
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()
            logger.info("ipc client disconnected")

    async def _send(self, writer: asyncio.StreamWriter, message) -> None:
        try:
            frame = protocol.encode(message)
        except ValueError as exc:  # response exceeds MAX_FRAME_BYTES
            frame = protocol.encode(protocol.ErrorResult(message=f"response too large: {exc}"))
        writer.write(frame)
        await writer.drain()

    async def serve_forever(self) -> None:
        self._paths.ensure_dir()
        lock_fd = acquire_startup_lock(self._paths)
        try:
            if self._paths.socket.exists():
                if socket_is_live(self._paths.socket):
                    raise RuntimeError("refusing to start: daemon socket already in use")
                self._paths.socket.unlink()  # stale leftover

            server = await asyncio.start_unix_server(
                self._handle_client,
                path=str(self._paths.socket),
                limit=protocol.MAX_FRAME_BYTES,
            )
            self._paths.pid.write_text(str(os.getpid()))
            logger.info("daemon listening on %s", self._paths.socket)

            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                with contextlib.suppress(NotImplementedError, RuntimeError):
                    loop.add_signal_handler(sig, stop.set)
            try:
                async with server:
                    task = asyncio.create_task(server.serve_forever())
                    await stop.wait()
                    logger.info("daemon shutting down")
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            finally:
                self._paths.socket.unlink(missing_ok=True)
                self._paths.pid.unlink(missing_ok=True)
        finally:
            os.close(lock_fd)
