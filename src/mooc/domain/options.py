"""Option domain types (pure data, no SDK/runtime dependency)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class OptionType(StrEnum):
    CALL = "CALL"
    PUT = "PUT"


class LegAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class OptionLeg:
    """One leg of an option strategy/combo."""

    code: str
    action: LegAction
    quantity: float


@dataclass(frozen=True)
class OptionContract:
    code: str
    underlying: str
    expiry: date
    strike: float
    option_type: OptionType
    multiplier: int = 100


@dataclass(frozen=True)
class OptionChain:
    underlying: str
    contracts: list[OptionContract]


@dataclass(frozen=True)
class OptionQuote:
    code: str
    last: float | None = None
    bid: float | None = None
    ask: float | None = None
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None
    oi: int | None = None
    volume: int | None = None


@dataclass(frozen=True)
class ComboAnalysis:
    """Combo-level quote and P&L from ``get_option_strategy_analysis``."""

    legs: list[OptionLeg]
    code: str
    name: str
    strategy: str
    bid1: float
    ask1: float
    max_profit: float
    max_loss: float
    breakeven: list[float]
    prob_profit: float
    delta: float
    theta: float
