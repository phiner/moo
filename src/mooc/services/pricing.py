"""Strategy pricing: pure payoff math for the V1.0 strategy set (spec ch. 5).

No SDK or I/O. Fill prices use the executable direction: buys pay the ask,
sells receive the bid; the configured :class:`CostModel` then adds slippage and
per-contract fees. Formulas follow the spec (5.1–5.7) and are covered by tests.
"""

from __future__ import annotations

from ..domain.strategy import DEFAULT_MULTIPLIER, CostModel, PricingResult, StrategyType

__all__ = [
    "bear_call_credit_spread",
    "bear_put_debit_spread",
    "bull_call_debit_spread",
    "bull_put_credit_spread",
    "cash_secured_put",
    "conversion",
    "covered_call",
]

_NO_COST = CostModel()


def _sell(bid: float, cost: CostModel) -> float:
    return bid - cost.slippage_per_share


def _buy(ask: float, cost: CostModel) -> float:
    return ask + cost.slippage_per_share


def _fees(cost: CostModel, contracts: int, legs: int) -> float:
    return cost.per_contract_fee * contracts * legs


def _positive_width(near: float, far: float) -> float:
    width = abs(near - far)
    if width == 0:
        raise ValueError("strikes must differ")
    return width


def bull_put_credit_spread(
    *,
    short_strike: float,
    long_strike: float,
    short_bid: float,
    long_ask: float,
    contracts: int = 1,
    multiplier: int = DEFAULT_MULTIPLIER,
    cost: CostModel = _NO_COST,
) -> PricingResult:
    """Sell higher-strike put, buy lower-strike put (spec 5.1)."""
    if short_strike <= long_strike:
        raise ValueError("bull put spread requires short_strike > long_strike")
    width = _positive_width(short_strike, long_strike)
    net_ps = _sell(short_bid, cost) - _buy(long_ask, cost)
    credit = net_ps * multiplier * contracts - _fees(cost, contracts, 2)
    max_loss = width * multiplier * contracts - credit
    return PricingResult(
        strategy=StrategyType.BULL_PUT_CREDIT_SPREAD,
        net_premium=credit,
        max_profit=credit,
        max_loss=max_loss,
        breakeven=[short_strike - net_ps],
    )


def bear_call_credit_spread(
    *,
    short_strike: float,
    long_strike: float,
    short_bid: float,
    long_ask: float,
    contracts: int = 1,
    multiplier: int = DEFAULT_MULTIPLIER,
    cost: CostModel = _NO_COST,
) -> PricingResult:
    """Sell lower-strike call, buy higher-strike call (spec 5.1)."""
    if short_strike >= long_strike:
        raise ValueError("bear call spread requires short_strike < long_strike")
    width = _positive_width(short_strike, long_strike)
    net_ps = _sell(short_bid, cost) - _buy(long_ask, cost)
    credit = net_ps * multiplier * contracts - _fees(cost, contracts, 2)
    max_loss = width * multiplier * contracts - credit
    return PricingResult(
        strategy=StrategyType.BEAR_CALL_CREDIT_SPREAD,
        net_premium=credit,
        max_profit=credit,
        max_loss=max_loss,
        breakeven=[short_strike + net_ps],
    )


def cash_secured_put(
    *,
    strike: float,
    put_bid: float,
    contracts: int = 1,
    multiplier: int = DEFAULT_MULTIPLIER,
    cost: CostModel = _NO_COST,
) -> PricingResult:
    """Sell a cash-secured put (spec 5.2). Cash covers assignment at ``strike``."""
    net_ps = _sell(put_bid, cost)
    premium = net_ps * multiplier * contracts - _fees(cost, contracts, 1)
    cash_required = strike * multiplier * contracts
    effective_entry = strike - net_ps
    max_loss = (strike - net_ps) * multiplier * contracts
    return PricingResult(
        strategy=StrategyType.CASH_SECURED_PUT,
        net_premium=premium,
        max_profit=premium,
        max_loss=max_loss,
        breakeven=[effective_entry],
        cash_required=cash_required,
        notes="assigns stock at strike; loss assumes underlying can fall toward 0",
    )


def covered_call(
    *,
    strike: float,
    call_bid: float,
    stock_cost: float | None = None,
    contracts: int = 1,
    multiplier: int = DEFAULT_MULTIPLIER,
    cost: CostModel = _NO_COST,
) -> PricingResult:
    """Sell a call against owned shares (spec 5.3).

    ``stock_cost`` (per-share entry) is needed for max profit/loss; without it
    only the premium and effective sale price are meaningful.
    """
    net_ps = _sell(call_bid, cost)
    premium = net_ps * multiplier * contracts - _fees(cost, contracts, 1)
    effective_sale = strike + net_ps
    max_profit: float | None = None
    max_loss: float | None = None
    breakeven: list[float] = []
    if stock_cost is not None:
        max_profit = (effective_sale - stock_cost) * multiplier * contracts
        max_loss = (stock_cost - net_ps) * multiplier * contracts
        breakeven = [stock_cost - net_ps]
    return PricingResult(
        strategy=StrategyType.COVERED_CALL,
        net_premium=premium,
        max_profit=max_profit,
        max_loss=max_loss,
        breakeven=breakeven,
        notes="stock downside risk remains; premium only partly offsets it",
    )


def bull_call_debit_spread(
    *,
    long_strike: float,
    short_strike: float,
    long_ask: float,
    short_bid: float,
    contracts: int = 1,
    multiplier: int = DEFAULT_MULTIPLIER,
    cost: CostModel = _NO_COST,
) -> PricingResult:
    """Buy lower-strike call, sell higher-strike call (spec 5.4)."""
    if long_strike >= short_strike:
        raise ValueError("bull call spread requires long_strike < short_strike")
    width = _positive_width(long_strike, short_strike)
    net_ps = _buy(long_ask, cost) - _sell(short_bid, cost)
    debit = net_ps * multiplier * contracts + _fees(cost, contracts, 2)
    max_profit = width * multiplier * contracts - debit
    return PricingResult(
        strategy=StrategyType.BULL_CALL_DEBIT_SPREAD,
        net_premium=-debit,
        max_profit=max_profit,
        max_loss=debit,
        breakeven=[long_strike + net_ps],
    )


def bear_put_debit_spread(
    *,
    long_strike: float,
    short_strike: float,
    long_ask: float,
    short_bid: float,
    contracts: int = 1,
    multiplier: int = DEFAULT_MULTIPLIER,
    cost: CostModel = _NO_COST,
) -> PricingResult:
    """Buy higher-strike put, sell lower-strike put (spec 5.4)."""
    if long_strike <= short_strike:
        raise ValueError("bear put spread requires long_strike > short_strike")
    width = _positive_width(long_strike, short_strike)
    net_ps = _buy(long_ask, cost) - _sell(short_bid, cost)
    debit = net_ps * multiplier * contracts + _fees(cost, contracts, 2)
    max_profit = width * multiplier * contracts - debit
    return PricingResult(
        strategy=StrategyType.BEAR_PUT_DEBIT_SPREAD,
        net_premium=-debit,
        max_profit=max_profit,
        max_loss=debit,
        breakeven=[long_strike - net_ps],
    )


def conversion(
    *,
    strike: float,
    stock_ask: float,
    put_ask: float,
    call_bid: float,
    contracts: int = 1,
    multiplier: int = DEFAULT_MULTIPLIER,
    dividends: float = 0.0,
    cost: CostModel = _NO_COST,
) -> PricingResult:
    """Long stock + long put + short call at one strike (spec 5.7).

    Held to expiry the payoff is ``strike`` (minus ``dividends`` foregone), so
    the result is the locked-in carry. Dividends must be supplied explicitly.
    """
    net_debit_ps = _buy(stock_ask, cost) + _buy(put_ask, cost) - _sell(call_bid, cost)
    net_debit = net_debit_ps * multiplier * contracts + _fees(cost, contracts, 3)
    value_at_expiry = strike * multiplier * contracts - dividends
    profit = value_at_expiry - net_debit
    return PricingResult(
        strategy=StrategyType.CONVERSION,
        net_premium=-net_debit,
        max_profit=profit,
        max_loss=profit,
        cash_required=net_debit,
        notes="conversion payoff is fixed at expiry (less dividends/early assignment risk)",
    )
