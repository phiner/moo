"""Local trading safety policy.

This client is SIMULATE-only by default; every trade request resolves its
environment through :func:`resolve_trd_env` so a disallowed environment (e.g.
REAL) fails fast with ``TradingDisabled`` instead of reaching OpenD.
"""

from __future__ import annotations

from .config import TradingConfig
from .opend.errors import TradingDisabled


def resolve_trd_env(requested: str | None, trading: TradingConfig) -> str:
    """Return the effective trade environment, enforcing the allowed set."""
    env = str(requested or trading.default_trd_env).upper()
    if env not in trading.allowed_trd_envs:
        allowed = ", ".join(trading.allowed_trd_envs)
        raise TradingDisabled(f"trading environment {env} is not allowed (allowed: {allowed})")
    return env
