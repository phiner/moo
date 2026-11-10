"""Forward performance from the trade journal (spec ch. 15).

Pure: computed only from recorded trades, never from history/backtests.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from ..domain.journal import TradeLogEntry
from ..domain.market import to_utc

__all__ = ["PerformanceReport", "report"]

_EPOCH = datetime.min.replace(tzinfo=UTC)


def _when(entry: TradeLogEntry) -> datetime:
    value = entry.closed_at or entry.opened_at
    return to_utc(value) if value is not None else _EPOCH


@dataclass(frozen=True)
class PerformanceReport:
    trades: int
    wins: int
    losses: int
    win_rate: float | None
    average_win: float | None
    average_loss: float | None
    profit_factor: float | None
    expectancy: float | None
    max_drawdown: float | None
    return_on_risk: float | None
    average_holding_period_days: float | None


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _max_drawdown(pnls: Sequence[float]) -> float | None:
    if not pnls:
        return None
    peak = cumulative = 0.0
    worst = 0.0
    for pnl in pnls:
        cumulative += pnl
        peak = max(peak, cumulative)
        worst = min(worst, cumulative - peak)
    return worst


def report(entries: Sequence[TradeLogEntry]) -> PerformanceReport:
    """Compute forward-performance metrics over entries that have a P&L."""
    closed = sorted(
        (entry for entry in entries if entry.pnl is not None),
        key=_when,
    )
    pnls = [float(entry.pnl) for entry in closed if entry.pnl is not None]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]

    gross_loss = abs(sum(losses))
    gross_win = sum(wins)
    risks = [float(e.max_loss) for e in closed if e.max_loss is not None]

    holding: list[float] = []
    for entry in closed:
        if entry.opened_at is not None and entry.closed_at is not None:
            holding.append((entry.closed_at - entry.opened_at).total_seconds() / 86400.0)

    return PerformanceReport(
        trades=len(pnls),
        wins=len(wins),
        losses=len(losses),
        win_rate=(len(wins) / len(pnls)) if pnls else None,
        average_win=_mean(wins),
        average_loss=_mean(losses),
        profit_factor=(gross_win / gross_loss) if gross_loss > 0 else None,
        expectancy=_mean(pnls),
        max_drawdown=_max_drawdown(pnls),
        return_on_risk=(sum(pnls) / sum(risks)) if risks and sum(risks) > 0 else None,
        average_holding_period_days=_mean(holding),
    )
