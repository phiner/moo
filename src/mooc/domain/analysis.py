"""Analysis request/response context types (P0.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

__all__ = [
    "AccountContext",
    "AnalysisContext",
    "AnalysisResultStatus",
    "AnalysisRunResult",
    "PersistenceStatus",
    "new_analysis_id",
]


class AnalysisResultStatus(StrEnum):
    OK = "OK"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    RULE_NOT_CONFIGURED = "RULE_NOT_CONFIGURED"
    INVALID_INPUT = "INVALID_INPUT"
    CALCULATION_ERROR = "CALCULATION_ERROR"
    STALE_DATA = "STALE_DATA"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"


@dataclass(frozen=True)
class PersistenceStatus:
    status: str  # saved | skipped | failed | not_attempted
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": self.status}
        if self.message:
            payload["message"] = self.message
        return payload


@dataclass(frozen=True)
class AccountContext:
    """Explicit account inputs for analysis; missing fields stay None."""

    account_id: int | None = None
    trd_env: str | None = None
    currency: str | None = None
    account_equity: float | None = None
    available_cash: float | None = None
    buying_power: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "trd_env": self.trd_env,
            "currency": self.currency,
            "account_equity": self.account_equity,
            "available_cash": self.available_cash,
            "buying_power": self.buying_power,
        }

    @property
    def has_sizing_equity(self) -> bool:
        return self.account_equity is not None and self.account_equity > 0


@dataclass(frozen=True)
class AnalysisContext:
    analysis_id: str
    symbol: str
    requested_at: datetime
    rules_version: str | None
    account: AccountContext | None = None
    market_snapshot_ref: str | None = None
    option_chain_snapshot_ref: str | None = None
    entrypoint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "symbol": self.symbol,
            "requested_at": self.requested_at.isoformat(),
            "rules_version": self.rules_version,
            "account": self.account.to_dict() if self.account else None,
            "market_snapshot_ref": self.market_snapshot_ref,
            "option_chain_snapshot_ref": self.option_chain_snapshot_ref,
            "entrypoint": self.entrypoint,
        }


@dataclass
class AnalysisRunResult:
    """Unified result of one analysis execution (compute + persistence outcome)."""

    output: Any  # DecisionOutput (kept loose to avoid import cycle in this module)
    analysis_id: str
    symbol: str
    requested_at: str
    rules_version: str | None
    analysis_status: str
    persistence: PersistenceStatus
    account: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)

    def to_response_payload(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "symbol": self.symbol,
            "requested_at": self.requested_at,
            "rules_version": self.rules_version,
            "analysis_status": self.analysis_status,
            "persistence": self.persistence.to_dict(),
            "account": self.account,
            "notes": list(self.notes),
        }


def new_analysis_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)
