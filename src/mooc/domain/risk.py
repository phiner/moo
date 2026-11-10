"""Risk domain types (pure data)."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ExitSignal", "Greeks", "PositionLeg", "TradeRisk"]


@dataclass(frozen=True)
class Greeks:
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0


@dataclass(frozen=True)
class PositionLeg:
    """One position leg; ``quantity`` is signed (+long / -short)."""

    greeks: Greeks
    quantity: float
    multiplier: int = 100


@dataclass(frozen=True)
class TradeRisk:
    max_loss_per_contract: float
    allowed_risk: float | None = None
    recommended_contracts: int | None = None
    risk_pct_of_equity: float | None = None
    passed: bool = False
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExitSignal:
    kind: str  # take_profit | stop_review | time_exit
    reason: str


#: Drawdown responses the policy may return (never a hard liquidation).
DRAWDOWN_ACTIONS = ("alert_only", "reduce_risk", "stop_new")
