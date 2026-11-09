"""Trade domain types (pure data, no SDK/runtime dependency)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TradeEnv(StrEnum):
    SIMULATE = "SIMULATE"
    REAL = "REAL"


@dataclass(frozen=True)
class Account:
    """One tradable account from ``get_acc_list``."""

    acc_id: int
    trd_env: str
    acc_type: str
    card_num: str
    security_firm: str
    sim_acc_type: str
    acc_status: str
    acc_role: str
    trdmarket_auth: list[str]


@dataclass(frozen=True)
class AccountFunds:
    """Account-level funds snapshot from ``accinfo_query``."""

    acc_id: int
    trd_env: str
    currency: str
    cash: float | None
    total_assets: float | None
    securities_assets: float | None
    market_val: float | None
    available_funds: float | None
    frozen_cash: float | None
    power: float | None
    unrealized_pl: float | None
    realized_pl: float | None
    initial_margin: float | None
    maintenance_margin: float | None
    risk_level: str


@dataclass(frozen=True)
class Position:
    """One open position from ``position_list_query``."""

    code: str
    stock_name: str
    position_market: str
    qty: float
    can_sell_qty: float
    cost_price: float | None
    average_cost: float | None
    nominal_price: float | None
    market_val: float | None
    pl_ratio: float | None
    pl_val: float | None
    unrealized_pl: float | None
    realized_pl: float | None
    currency: str
    position_side: str
    strategy_type: str


@dataclass(frozen=True)
class Order:
    """One order from ``order_list_query`` / ``history_order_list_query``."""

    code: str
    stock_name: str
    order_market: str
    trd_side: str
    order_type: str
    order_status: str
    order_id: str
    qty: float
    price: float
    dealt_qty: float
    dealt_avg_price: float
    create_time: str
    updated_time: str
    time_in_force: str
    currency: str
    remark: str
    last_err_msg: str
