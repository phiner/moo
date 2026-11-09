"""Event calendar domain types (pure data, no SDK/runtime dependency)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .market import DataSource, to_utc

__all__ = ["Event", "EventType"]


class EventType(StrEnum):
    EARNINGS = "earnings"
    ECONOMIC = "economic"
    DIVIDEND = "dividend"
    OTHER = "other"


@dataclass(frozen=True)
class Event:
    """One calendar event; ``code`` is ``None`` for market-wide (macro) events."""

    event_type: EventType
    event_datetime: datetime
    observed_at: datetime
    code: str | None = None
    status: str = "upcoming"
    source: DataSource = DataSource.UNKNOWN
    payload: str = "{}"

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_datetime", to_utc(self.event_datetime))
        object.__setattr__(self, "observed_at", to_utc(self.observed_at))
