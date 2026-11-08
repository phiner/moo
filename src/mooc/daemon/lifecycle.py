"""Daemon runtime paths, startup lock, and liveness helpers."""

from __future__ import annotations

import fcntl
import os
import socket
from dataclasses import dataclass
from pathlib import Path

from ..opend.errors import MoocError


@dataclass(frozen=True)
class DaemonPaths:
    runtime_dir: Path
    socket: Path
    pid: Path
    lock: Path

    def ensure_dir(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    def readable_pid(self) -> int | None:
        try:
            return int(self.pid.read_text().strip())
        except (FileNotFoundError, ValueError):
            return None


def daemon_paths(runtime_dir: Path | None = None) -> DaemonPaths:
    base = runtime_dir or Path(os.environ.get("MOOC_RUNTIME_DIR", "~/.mooc")).expanduser()
    return DaemonPaths(
        runtime_dir=base,
        socket=base / "mooc.sock",
        pid=base / "mooc.pid",
        lock=base / "mooc.lock",
    )


def is_running(paths: DaemonPaths) -> bool:
    pid = paths.readable_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def socket_is_live(path: Path, timeout: float = 0.5) -> bool:
    """True if something is accepting connections on the unix socket."""
    if not path.exists():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(path))
        return True
    except OSError:
        return False


def acquire_startup_lock(paths: DaemonPaths) -> int:
    """Atomically claim the daemon startup lock; return the held fd.

    Raises MoocError if another daemon already holds the lock. The caller keeps
    the fd open for the process lifetime and closes it on exit.
    """
    paths.ensure_dir()
    fd = os.open(paths.lock, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        raise MoocError("daemon already running (startup lock held)") from exc
    return fd
