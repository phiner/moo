from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from mooc.domain.journal import TradeLogEntry
from mooc.services import journal

BASE = datetime(2026, 11, 1, 15, 0, tzinfo=UTC)


def _entry(pnl, *, opened, closed, max_loss=400.0, status="CLOSED"):
    return TradeLogEntry(
        symbol="US.AAPL",
        strategy="bull_put_credit_spread",
        status=status,
        opened_at=opened,
        closed_at=closed,
        max_loss=max_loss,
        pnl=pnl,
    )


def test_report_metrics():
    entries = [
        _entry(200.0, opened=BASE, closed=BASE + timedelta(days=10)),
        _entry(-100.0, opened=BASE, closed=BASE + timedelta(days=20)),
        _entry(50.0, opened=BASE, closed=BASE + timedelta(days=30)),
    ]
    result = journal.report(entries)
    assert result.trades == 3
    assert result.wins == 2
    assert result.losses == 1
    assert result.win_rate == pytest.approx(2 / 3)
    assert result.average_win == pytest.approx(125.0)
    assert result.average_loss == pytest.approx(-100.0)
    assert result.profit_factor == pytest.approx(2.5)  # 250 gross win / 100 gross loss
    assert result.expectancy == pytest.approx(50.0)
    assert result.max_drawdown == pytest.approx(-100.0)  # 200 -> 100 (peak 200)
    assert result.return_on_risk == pytest.approx(150.0 / 1200.0)
    assert result.average_holding_period_days == pytest.approx(20.0)


def test_report_ignores_open_positions_and_handles_empty():
    empty = journal.report([])
    assert empty.trades == 0
    assert empty.win_rate is None
    assert empty.profit_factor is None
    assert empty.expectancy is None
    assert empty.max_drawdown is None

    open_only = journal.report([_entry(None, opened=BASE, closed=None, status="OPEN")])
    assert open_only.trades == 0
    assert open_only.expectancy is None


def test_profit_factor_none_without_losses():
    result = journal.report([_entry(100.0, opened=BASE, closed=BASE + timedelta(days=1))])
    assert result.profit_factor is None
    assert result.win_rate == 1.0
