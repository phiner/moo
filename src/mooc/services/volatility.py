"""Volatility analytics: IV Rank / IV Percentile and IV-vs-HV comparison.

Pure functions over a daily IV/HV series — no SDK or I/O, so they are fully
unit-testable. The spec leaves the exact thresholds open (chapter 18); this
module only computes, it never decides.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..domain.market import VolatilityPoint

__all__ = ["VolatilitySummary", "iv_percentile", "iv_rank", "summarize"]

IV_RANK_LOOKBACK = 252


def iv_rank(values: Sequence[float], current: float) -> float:
    """Position of ``current`` within ``values`` as 0–100 (0 when no range)."""
    low, high = min(values), max(values)
    if high == low:
        return 0.0
    return (current - low) / (high - low) * 100.0


def iv_percentile(values: Sequence[float], current: float) -> float:
    """Share of ``values`` strictly below ``current``, as 0–100."""
    if not values:
        return 0.0
    below = sum(1 for value in values if value < current)
    return below / len(values) * 100.0


@dataclass(frozen=True)
class VolatilitySummary:
    iv: float | None
    hv: float | None
    iv_rank: float | None
    iv_percentile: float | None
    iv_hv_diff: float | None


def summarize(
    points: Sequence[VolatilityPoint], *, lookback: int = IV_RANK_LOOKBACK
) -> VolatilitySummary:
    """Summarize the most recent IV/HV with rank/percentile over ``lookback`` days."""
    series = [point for point in points if point.iv is not None]
    if not series:
        return VolatilitySummary(None, None, None, None, None)
    window = series[-lookback:]
    latest = window[-1]
    values = [point.iv for point in window if point.iv is not None]
    current = latest.iv
    assert current is not None  # enforced by the filter above
    return VolatilitySummary(
        iv=current,
        hv=latest.hv,
        iv_rank=iv_rank(values, current),
        iv_percentile=iv_percentile(values, current),
        iv_hv_diff=(current - latest.hv) if latest.hv is not None else None,
    )
