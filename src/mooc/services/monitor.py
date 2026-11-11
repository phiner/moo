"""Position monitoring: turn live leg prices into exit signals.

Pure. ``cost_to_close`` is the executable price to flatten the position now
(buy back shorts at the ask, sell longs at the bid); it returns ``None`` when any
needed quote is missing, so callers never act on partial data.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..domain.risk import ExitSignal
from .risk import exit_signals

__all__ = ["MonitoredLeg", "cost_to_close", "monitor_position"]

MULTIPLIER = 100


@dataclass(frozen=True)
class MonitoredLeg:
    code: str
    action: str  # BUY | SELL
    quantity: float
    bid: float | None = None
    ask: float | None = None


def cost_to_close(legs: Sequence[MonitoredLeg]) -> float | None:
    """Per-share cost to flatten now, or ``None`` if a required quote is missing.

    Buy back shorts at the ask, sell longs at the bid. The result is in the same
    per-share premium units as strategy ``net_credit`` / ``average_cost`` so it can
    feed :func:`exit_signals` directly.
    """
    total = 0.0
    for leg in legs:
        if leg.action.upper() == "SELL":
            if leg.ask is None:
                return None
            total += leg.ask
        else:
            if leg.bid is None:
                return None
            total -= leg.bid
    return total


def monitor_position(
    *,
    legs: Sequence[MonitoredLeg],
    entry_credit: float,
    dte: int | None,
    take_profit_pct: float | None = None,
    stop_review_multiple: float | None = None,
    time_exit_dte: int | None = None,
) -> list[ExitSignal]:
    """Return exit signals for one open position."""
    cost = cost_to_close(legs)
    return exit_signals(
        cost_to_close=cost,
        net_credit=entry_credit,
        dte=dte,
        take_profit_pct=take_profit_pct,
        stop_review_multiple=stop_review_multiple,
        time_exit_dte=time_exit_dte,
    )
