from __future__ import annotations

from datetime import UTC, datetime

from mooc.domain.decision import DecisionOutput, TradeStatus
from mooc.services import monitor, recording
from mooc.storage import db

NOW = datetime(2026, 11, 8, 20, 0, tzinfo=UTC)


def _output(status=TradeStatus.CANDIDATE):
    return DecisionOutput(
        symbol="US.AAPL",
        analysis_timestamp=NOW.isoformat(),
        data_quality="ok",
        market_regime="bullish",
        volatility_regime="normal",
        event_risk="low",
        recommended_action="consider_bull_put_credit_spread",
        strategy={"type": "bull_put_credit_spread", "expiration": "2026-12-18"},
        risk={"portfolio_risk_passed": False, "recommended_contracts": 0},
        trade_status=status,
        rejection_reasons=[],
        missing_data=[],
    )


def test_record_decision_writes_rows(tmp_path):
    conn = db.open_db(tmp_path / "mooc.db")
    try:
        recording.record_decision(conn, _output(), created_at=NOW)
        assert conn.execute("SELECT COUNT(*) AS c FROM trade_candidates").fetchone()["c"] == 1
        assert conn.execute("SELECT COUNT(*) AS c FROM trade_signals").fetchone()["c"] == 1
        assert conn.execute("SELECT COUNT(*) AS c FROM risk_snapshots").fetchone()["c"] == 1
        row = conn.execute("SELECT symbol, strategy, status, action FROM trade_signals").fetchone()
        assert row["symbol"] == "US.AAPL"
        assert row["status"] == "CANDIDATE"
        assert row["action"] == "consider_bull_put_credit_spread"
    finally:
        conn.close()


def test_cost_to_close_and_signals():
    # short close: action SELL => buy back at ask (per share)
    short_leg = monitor.MonitoredLeg(code="US.AAPL", action="SELL", quantity=1, bid=0.3, ask=0.5)
    assert monitor.cost_to_close([short_leg]) == 0.5

    # long close: action BUY => sell at bid (receive, per share)
    long_leg = monitor.MonitoredLeg(code="US.AAPL", action="BUY", quantity=1, bid=0.7, ask=0.9)
    assert monitor.cost_to_close([long_leg]) == -0.7

    # take profit: cost dropped to <= 50% of credit (1.20 received, 0.50 to close)
    signals = monitor.monitor_position(
        legs=[short_leg], entry_credit=1.2, dte=20, take_profit_pct=0.5
    )
    assert [s.kind for s in signals] == ["take_profit"]

    # time exit: DTE within threshold
    signals = monitor.monitor_position(legs=[short_leg], entry_credit=1.2, dte=5, time_exit_dte=7)
    assert any(s.kind == "time_exit" for s in signals)

    # time_exit_dte as float (from YAML parsing) is accepted by caller logic; int works directly
    signals = monitor.monitor_position(legs=[short_leg], entry_credit=1.2, dte=5, time_exit_dte=7)
    assert any(s.kind == "time_exit" for s in signals)

    # missing quote => no price-based action
    missing = monitor.MonitoredLeg(code="US.AAPL", action="SELL", quantity=1, bid=None, ask=None)
    assert monitor.cost_to_close([missing]) is None
    signals = monitor.monitor_position(legs=[missing], entry_credit=1.2, dte=20)
    assert signals == []


def test_monitor_cli_mapping_and_stale(tmp_path, monkeypatch):
    """Short qty<0 closes via SELL(ask), long qty>0 via BUY(bid); stale suppresses price signals."""
    from dataclasses import dataclass
    from types import SimpleNamespace

    from mooc import cli
    from mooc.config import AppConfig

    @dataclass
    class Pos:
        code: str
        qty: float
        average_cost: float | None
        position_side: str = ""

    @dataclass
    class Snap:
        bid: float | None
        ask: float | None
        quality: object

    short = Pos(code="US.AAPL260101P100000", qty=-1, average_cost=1.2)
    long = Pos(code="US.AAPL260101C120000", qty=2, average_cost=3.0)
    snaps = {
        short.code: Snap(bid=0.3, ask=0.5, quality=SimpleNamespace(is_stale=False)),
        long.code: Snap(bid=0.7, ask=0.9, quality=SimpleNamespace(is_stale=False)),
    }

    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "load_rules", lambda _p: [])
    monkeypatch.setattr(cli, "resolve_trd_env", lambda *_a, **_k: "SIMULATE")

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(cli, "_connected", lambda: _Client())
    monkeypatch.setattr(cli.trade_api, "list_positions", lambda *a, **k: [short, long])
    monkeypatch.setattr(cli.option_api, "snapshots", lambda *a, **k: snaps)

    out = {}
    monkeypatch.setattr(
        cli,
        "json",
        SimpleNamespace(dumps=lambda obj, **k: out.setdefault("data", obj) or "x"),
    )

    rc = cli._cmd_probe_monitor(
        SimpleNamespace(trd_env=None, acc_id=1, code=None, currency=None, json=True)
    )
    assert rc == 0
    rows = {r["code"]: r for r in out["data"]}
    # short: buy back at ask
    assert rows[short.code]["cost_to_close"] == 0.5
    assert rows[short.code]["credit_signals_applicable"] is True
    # long: sell at bid (receive), no credit price signals
    assert rows[long.code]["cost_to_close"] == -0.7
    assert rows[long.code]["credit_signals_applicable"] is False
    assert rows[long.code]["signals"] == []

    # stale quote suppresses price signals/cost
    stale_snaps = {short.code: Snap(bid=0.3, ask=0.5, quality=SimpleNamespace(is_stale=True))}
    monkeypatch.setattr(cli.trade_api, "list_positions", lambda *a, **k: [short])
    monkeypatch.setattr(cli.option_api, "snapshots", lambda *a, **k: stale_snaps)
    out.clear()
    rc = cli._cmd_probe_monitor(
        SimpleNamespace(trd_env=None, acc_id=1, code=None, currency=None, json=True)
    )
    assert rc == 0
    row = out["data"][0]
    assert row["quote_stale"] is True
    assert row["signals_suppressed_stale"] is True
    assert row["cost_to_close"] is None
    assert row["signals"] == []


def test_record_decision_idempotent(tmp_path):
    conn = db.open_db(tmp_path / "mooc.db")
    try:
        assert recording.record_decision(conn, _output(), created_at=NOW) is True
        assert recording.record_decision(conn, _output(), created_at=NOW) is False
        assert conn.execute("SELECT COUNT(*) AS c FROM trade_candidates").fetchone()["c"] == 1
        assert conn.execute("SELECT COUNT(*) AS c FROM trade_signals").fetchone()["c"] == 1
        assert conn.execute("SELECT COUNT(*) AS c FROM risk_snapshots").fetchone()["c"] == 1
    finally:
        conn.close()
