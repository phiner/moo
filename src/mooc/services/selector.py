"""Option contract selection for vertical spreads (spec ch. 3.1D / 5.1 / 5.4).

Pure: callers supply contracts with bid/ask/delta. Picking is deterministic —
the expiry nearest the DTE target and the short strike nearest the delta target,
then the long strike at the requested width. Missing/undetermined bounds yield an
explicit reason instead of a guess.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from ..domain.options import OptionType
from ..domain.strategy import StrategyType

__all__ = ["ContractQuote", "SelectionOutcome", "SpreadSelection", "select_spread", "shape_for"]


@dataclass(frozen=True)
class ContractQuote:
    code: str
    expiry: date
    strike: float
    option_type: OptionType
    bid: float | None = None
    ask: float | None = None
    delta: float | None = None
    open_interest: int | None = None
    volume: int | None = None


@dataclass(frozen=True)
class SpreadSelection:
    expiry: date
    dte: int
    short: ContractQuote
    long: ContractQuote
    width: float
    is_credit: bool
    net_per_share: float
    delta: float | None


@dataclass(frozen=True)
class SelectionOutcome:
    selection: SpreadSelection | None
    reasons: tuple[str, ...] = ()


# strategy -> (option_type, short strike is higher than long, is_credit)
_SHAPES: dict[str, tuple[OptionType, bool, bool]] = {
    StrategyType.BULL_PUT_CREDIT_SPREAD: (OptionType.PUT, True, True),
    StrategyType.BEAR_CALL_CREDIT_SPREAD: (OptionType.CALL, False, True),
    StrategyType.BULL_CALL_DEBIT_SPREAD: (OptionType.CALL, True, False),
    StrategyType.BEAR_PUT_DEBIT_SPREAD: (OptionType.PUT, False, False),
}


def shape_for(strategy_name: str) -> tuple[OptionType, bool, bool] | None:
    return _SHAPES.get(strategy_name)


def _midpoint(low: float | None, high: float | None) -> float | None:
    if low is not None and high is not None:
        return (low + high) / 2
    return high if low is None else low


def select_spread(
    contracts: Sequence[ContractQuote],
    *,
    today: date,
    option_type: OptionType,
    short_is_higher: bool,
    is_credit: bool,
    min_dte: float | None,
    max_dte: float | None,
    delta_min: float | None,
    delta_max: float | None,
    min_width: float | None,
    max_width: float | None,
) -> SelectionOutcome:
    if not contracts:
        return SelectionOutcome(None, ("no contracts available",))

    dte_target = _midpoint(min_dte, max_dte)
    delta_target = _midpoint(delta_min, delta_max)
    width_target = _midpoint(min_width, max_width)
    if delta_target is None:
        return SelectionOutcome(None, ("delta bounds undetermined",))
    if width_target is None:
        return SelectionOutcome(None, ("width bounds undetermined",))

    usable = [
        contract
        for contract in contracts
        if contract.option_type is option_type
        and contract.bid is not None
        and contract.ask is not None
        and contract.delta is not None
    ]
    if not usable:
        return SelectionOutcome(None, ("no contracts with bid/ask/delta",))

    by_expiry: dict[date, list[ContractQuote]] = {}
    for contract in usable:
        by_expiry.setdefault(contract.expiry, []).append(contract)

    def dte_of(expiry: date) -> int:
        return (expiry - today).days

    expiries = [
        expiry
        for expiry in by_expiry
        if (min_dte is None or dte_of(expiry) >= min_dte)
        and (max_dte is None or dte_of(expiry) <= max_dte)
    ]
    if not expiries:
        return SelectionOutcome(None, ("no expiry within DTE bounds",))
    expiry = min(expiries, key=lambda value: abs(dte_of(value) - (dte_target or dte_of(value))))
    dte = dte_of(expiry)

    pool = by_expiry[expiry]
    # Put deltas are negative; rule bounds are magnitudes, so match |delta|.
    magnitude_target = abs(delta_target)
    short = min(pool, key=lambda contract: abs(abs(contract.delta or 0.0) - magnitude_target))
    width = abs(width_target)
    long_strike = short.strike - width if short_is_higher else short.strike + width
    long = min(pool, key=lambda contract: abs(contract.strike - long_strike))

    real_width = abs(short.strike - long.strike)
    if real_width == 0:
        return SelectionOutcome(None, ("short and long strikes coincide",))
    if min_width is not None and real_width < min_width:
        return SelectionOutcome(
            None, (f"nearest long leg width {real_width} below min {min_width}",)
        )
    if max_width is not None and real_width > max_width:
        return SelectionOutcome(
            None, (f"nearest long leg width {real_width} above max {max_width}",)
        )
    if is_credit:
        # sell short bid, buy long ask
        net_per_share = float(short.bid or 0.0) - float(long.ask or 0.0)
    else:
        net_per_share = float(long.ask or 0.0) - float(short.bid or 0.0)

    return SelectionOutcome(
        SpreadSelection(
            expiry=expiry,
            dte=dte,
            short=short,
            long=long,
            width=real_width,
            is_credit=is_credit,
            net_per_share=net_per_share,
            delta=abs(short.delta) if short.delta is not None else None,
        )
    )
