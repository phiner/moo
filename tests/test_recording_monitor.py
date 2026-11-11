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
    # short 1 contract (sold for credit): close by buying back at ask (per share)
    short_leg = monitor.MonitoredLeg(code="US.AAPL", action="SELL", quantity=1, bid=0.3, ask=0.5)
    assert monitor.cost_to_close([short_leg]) == 0.5

    # take profit: cost dropped to <= 50% of credit (1.20 received, 0.50 to close)
    signals = monitor.monitor_position(
        legs=[short_leg], entry_credit=1.2, dte=20, take_profit_pct=0.5
    )
    assert any(s.kind == "take_profit" for s in signals)

    # time exit: DTE within threshold
    signals = monitor.monitor_position(legs=[short_leg], entry_credit=1.2, dte=5, time_exit_dte=7)
    assert any(s.kind == "time_exit" for s in signals)

    # missing quote => no price-based action
    missing = monitor.MonitoredLeg(code="US.AAPL", action="SELL", quantity=1, bid=None, ask=None)
    assert monitor.cost_to_close([missing]) is None
    signals = monitor.monitor_position(legs=[missing], entry_credit=1.2, dte=20)
    assert signals == []
