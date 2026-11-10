"""Decision output and trade status machine (spec ch. 14.1 / 14.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..opend.errors import MoocError

__all__ = ["DecisionOutput", "TradeStatus", "can_transition", "transition"]


class TradeStatus(StrEnum):
    SCANNED = "SCANNED"
    ANALYZED = "ANALYZED"
    CANDIDATE = "CANDIDATE"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    READY = "READY"
    APPROVED = "APPROVED"
    OPEN = "OPEN"
    MONITORING = "MONITORING"
    EXIT_SIGNAL = "EXIT_SIGNAL"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


_ABORT = frozenset({TradeStatus.REJECTED, TradeStatus.INVALIDATED, TradeStatus.EXPIRED})

_ALLOWED: dict[TradeStatus, frozenset[TradeStatus]] = {
    TradeStatus.SCANNED: frozenset({TradeStatus.ANALYZED}) | _ABORT,
    TradeStatus.ANALYZED: frozenset({TradeStatus.CANDIDATE}) | _ABORT,
    TradeStatus.CANDIDATE: frozenset({TradeStatus.PENDING_CONFIRMATION}) | _ABORT,
    TradeStatus.PENDING_CONFIRMATION: frozenset({TradeStatus.READY}) | _ABORT,
    TradeStatus.READY: frozenset({TradeStatus.APPROVED}) | _ABORT,
    TradeStatus.APPROVED: frozenset({TradeStatus.OPEN}) | _ABORT,
    TradeStatus.OPEN: frozenset(
        {
            TradeStatus.MONITORING,
            TradeStatus.EXIT_SIGNAL,
            TradeStatus.CLOSED,
            TradeStatus.INVALIDATED,
        }
    ),
    TradeStatus.MONITORING: frozenset(
        {TradeStatus.EXIT_SIGNAL, TradeStatus.CLOSED, TradeStatus.INVALIDATED}
    ),
    TradeStatus.EXIT_SIGNAL: frozenset({TradeStatus.CLOSED}),
    TradeStatus.CLOSED: frozenset(),
    TradeStatus.REJECTED: frozenset(),
    TradeStatus.INVALIDATED: frozenset(),
    TradeStatus.EXPIRED: frozenset(),
}


def can_transition(current: TradeStatus, target: TradeStatus) -> bool:
    return target in _ALLOWED[current]


def transition(current: TradeStatus, target: TradeStatus) -> TradeStatus:
    """Return ``target`` if the move is legal, else raise ``MoocError``."""
    if not can_transition(current, target):
        raise MoocError(f"illegal status transition: {current} -> {target}")
    return target


@dataclass(frozen=True)
class DecisionOutput:
    """Standard analysis output (spec 14.1). ``None`` means "not determined"."""

    symbol: str
    analysis_timestamp: str
    data_quality: str
    recommended_action: str
    trade_status: TradeStatus
    market_regime: str | None = None
    volatility_regime: str | None = None
    event_risk: str | None = None
    strategy: dict[str, object] = field(default_factory=dict)
    risk: dict[str, object] = field(default_factory=dict)
    entry_conditions: list[str] = field(default_factory=list)
    exit_conditions: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "analysis_timestamp": self.analysis_timestamp,
            "data_quality": self.data_quality,
            "market_regime": self.market_regime,
            "volatility_regime": self.volatility_regime,
            "event_risk": self.event_risk,
            "recommended_action": self.recommended_action,
            "trade_status": self.trade_status.value,
            "strategy": self.strategy,
            "risk": self.risk,
            "entry_conditions": self.entry_conditions,
            "exit_conditions": self.exit_conditions,
            "rejection_reasons": self.rejection_reasons,
            "missing_data": self.missing_data,
        }
