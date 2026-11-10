"""Strategy rule types with tri-state fields (spec ch. 14 / 18).

Every constraint is tri-state:

- a concrete value  -> enforce it;
- ``None``          -> the key was present but ``null``: *undetermined*, so the
  strategy is not ready and must become NO TRADE (spec ch. 18: the agent must
  never invent a value);
- ``UNSET``         -> the key was absent: not applicable, skip it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = ["UNSET", "Maybe", "Regimes", "StrategyRule", "Unset"]


class Unset:
    """Sentinel for an absent rule key (distinct from a present ``null``)."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


UNSET: Final = Unset()

Maybe = float | None | Unset
Regimes = tuple[str, ...] | None | Unset


@dataclass(frozen=True)
class StrategyRule:
    """One strategy rule, mirroring the YAML shape in spec ch. 14."""

    name: str
    enabled: bool = True
    allowed_regimes: Regimes = UNSET
    iv_rank_min: Maybe = UNSET
    iv_rank_max: Maybe = UNSET
    iv_percentile_min: Maybe = UNSET
    min_dte: Maybe = UNSET
    max_dte: Maybe = UNSET
    delta_min: Maybe = UNSET
    delta_max: Maybe = UNSET
    min_width: Maybe = UNSET
    max_width: Maybe = UNSET
    take_profit_pct: Maybe = UNSET
    stop_review_multiple: Maybe = UNSET
    time_exit_dte: Maybe = UNSET
    max_account_risk_pct: Maybe = UNSET

    def undetermined(self) -> tuple[str, ...]:
        """Names of fields that are present-but-null (i.e. not yet determined)."""
        names = (
            "allowed_regimes",
            "iv_rank_min",
            "iv_rank_max",
            "iv_percentile_min",
            "min_dte",
            "max_dte",
            "delta_min",
            "delta_max",
            "min_width",
            "max_width",
            "take_profit_pct",
            "stop_review_multiple",
            "time_exit_dte",
            "max_account_risk_pct",
        )
        return tuple(name for name in names if getattr(self, name) is None)
