"""Synchronous IPC client used by the CLI and the TUI."""

from __future__ import annotations

import socket
from pathlib import Path

from ..opend.errors import MoocError
from . import protocol


class IpcClient:
    def __init__(self, socket_path: Path, timeout: float = 15.0) -> None:
        self._path = Path(socket_path)
        self._timeout = timeout

    def request(self, request) -> protocol.Response:
        """Send one request and return one response, wrapping all failures as MoocError."""
        if not self._path.exists():
            raise MoocError(f"daemon socket not found: {self._path} (is the daemon running?)")
        buffer = bytearray()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self._timeout)
                try:
                    sock.connect(str(self._path))
                except OSError as exc:
                    raise MoocError(f"cannot connect to daemon at {self._path}: {exc}") from exc
                try:
                    sock.sendall(protocol.encode(request))
                except OSError as exc:
                    raise MoocError(f"failed to send request: {exc}") from exc
                while not buffer.endswith(b"\n"):
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    buffer.extend(chunk)
                    if len(buffer) > protocol.MAX_FRAME_BYTES:
                        raise MoocError("response exceeds MAX_FRAME_BYTES")
        except OSError as exc:  # socket.timeout and friends
            raise MoocError(f"ipc transport error: {exc}") from exc
        if not buffer:
            raise MoocError("empty response from daemon")
        try:
            return protocol.decode_response(bytes(buffer))
        except Exception as exc:
            raise MoocError(f"invalid response from daemon: {exc}") from exc
