"""Trade journal and confirmation domain types (pure data, spec ch. 12.5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

__all__ = ["Confirmation", "TradeLogEntry"]


@dataclass(frozen=True)
class TradeLogEntry:
    """One recorded trade; ``pnl`` (dollars) drives forward performance."""

    symbol: str
    strategy: str
    status: str
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    entry_credit: float | None = None
    exit_cost: float | None = None
    max_loss: float | None = None
    pnl: float | None = None
    notes: str = ""


@dataclass(frozen=True)
class Confirmation:
    """A user's manual confirmation of a decision (never an order)."""

    symbol: str
    strategy: str
    confirmed_at: datetime
    payload: str = "{}"
