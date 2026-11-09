from __future__ import annotations

import argparse
from pathlib import Path

from mooc import cli
from mooc.daemon.lifecycle import daemon_paths


class _Process:
    pid = 32145

    def __init__(self, returncode: int | None = None) -> None:
        self.returncode = returncode
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def wait(self, timeout=None):
        return self.returncode


def test_daemon_run_detaches_and_waits_for_socket(tmp_path: Path, monkeypatch, capsys):
    paths = daemon_paths(tmp_path)
    process = _Process()
    monkeypatch.setattr(cli, "daemon_paths", lambda: paths)
    monkeypatch.setattr(cli, "is_running", lambda _paths: False)
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(cli, "socket_is_live", lambda _path: True)
    paths.pid.write_text(str(process.pid))

    result = cli._cmd_daemon_run(argparse.Namespace())

    assert result == 0
    output = capsys.readouterr().out
    assert "running in background" in output
    assert str(paths.log) in output


def test_daemon_run_reports_early_child_exit(tmp_path: Path, monkeypatch, capsys):
    paths = daemon_paths(tmp_path)
    paths.log.write_text("OpenD is unavailable\n")
    process = _Process(returncode=1)
    monkeypatch.setattr(cli, "daemon_paths", lambda: paths)
    monkeypatch.setattr(cli, "is_running", lambda _paths: False)
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *args, **kwargs: process)

    result = cli._cmd_daemon_run(argparse.Namespace())

    assert result == 1
    output = capsys.readouterr().err
    assert "exited during startup" in output
    assert "OpenD is unavailable" in output


def test_daemon_run_stops_child_when_startup_times_out(tmp_path: Path, monkeypatch, capsys):
    paths = daemon_paths(tmp_path)
    process = _Process()
    monkeypatch.setattr(cli, "daemon_paths", lambda: paths)
    monkeypatch.setattr(cli, "is_running", lambda _paths: False)
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(cli, "socket_is_live", lambda _path: False)
    ticks = iter([0.0, 11.0])
    monkeypatch.setattr(cli.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)

    result = cli._cmd_daemon_run(argparse.Namespace())

    assert result == 1
    assert process.terminated
    assert "startup timed out" in capsys.readouterr().err


def test_daemon_run_does_not_start_duplicate(tmp_path: Path, monkeypatch, capsys):
    paths = daemon_paths(tmp_path)
    monkeypatch.setattr(cli, "daemon_paths", lambda: paths)
    monkeypatch.setattr(cli, "is_running", lambda _paths: True)
    monkeypatch.setattr(
        cli.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not spawn")),
    )

    result = cli._cmd_daemon_run(argparse.Namespace())

    assert result == 1
    assert "already running" in capsys.readouterr().err
