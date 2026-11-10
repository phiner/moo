"""Strategy domain types: types, cost model, and pricing results (pure data)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = ["CostModel", "PricingResult", "StrategyType"]

DEFAULT_MULTIPLIER = 100


class StrategyType(StrEnum):
    BULL_PUT_CREDIT_SPREAD = "bull_put_credit_spread"
    BEAR_CALL_CREDIT_SPREAD = "bear_call_credit_spread"
    CASH_SECURED_PUT = "cash_secured_put"
    COVERED_CALL = "covered_call"
    BULL_CALL_DEBIT_SPREAD = "bull_call_debit_spread"
    BEAR_PUT_DEBIT_SPREAD = "bear_put_debit_spread"
    CONVERSION = "conversion"


@dataclass(frozen=True)
class CostModel:
    """Configurable fees and slippage (spec leaves exact values open, ch. 18).

    ``per_contract_fee`` is charged once per contract (per leg); ``slippage``
    is a per-share haircut that worsens every fill (buys pay more, sells get less).
    """

    per_contract_fee: float = 0.0
    slippage_per_share: float = 0.0


@dataclass(frozen=True)
class PricingResult:
    """Economics of one strategy. Amounts are in dollars for the whole position."""

    strategy: StrategyType
    net_premium: float  # > 0 = credit received, < 0 = debit paid
    max_profit: float | None
    max_loss: float | None
    breakeven: list[float] = field(default_factory=list)
    cash_required: float | None = None
    notes: str = ""

    @property
    def is_credit(self) -> bool:
        return self.net_premium >= 0
