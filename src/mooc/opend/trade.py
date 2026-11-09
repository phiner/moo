"""Trade data access built on the official ``moomoo-api`` SDK.

All queries are read-only. The trade environment is resolved (and policy-checked)
by the caller before it reaches here.
"""

from __future__ import annotations

from ..domain.trade import Account, AccountFunds, Order, Position
from .client import OpendClient
from .values import require_ok as _require_ok
from .values import to_float as _num


def _text(value) -> str:
    return "" if value is None else str(value)


def list_accounts(client: OpendClient, trd_env: str) -> list[Account]:
    """Return accounts for ``trd_env`` (US market)."""
    ret, data = client.trade_ctx.get_acc_list()
    _require_ok("get_acc_list", ret, data)
    accounts = []
    for _, row in data.iterrows():
        if _text(row.get("trd_env")) != trd_env:
            continue
        accounts.append(
            Account(
                acc_id=int(row["acc_id"]),
                trd_env=_text(row.get("trd_env")),
                acc_type=_text(row.get("acc_type")),
                card_num=_text(row.get("card_num")),
                security_firm=_text(row.get("security_firm")),
                sim_acc_type=_text(row.get("sim_acc_type")),
                acc_status=_text(row.get("acc_status")),
                acc_role=_text(row.get("acc_role")),
                trdmarket_auth=[_text(x) for x in (row.get("trdmarket_auth") or [])],
            )
        )
    return accounts


def get_funds(
    client: OpendClient, trd_env: str, acc_id: int, currency: str = "USD"
) -> AccountFunds | None:
    """Return the funds snapshot for ``acc_id`` in ``trd_env``."""
    ret, data = client.trade_ctx.accinfo_query(trd_env=trd_env, acc_id=acc_id, currency=currency)
    _require_ok("accinfo_query", ret, data)
    if len(data) == 0:
        return None
    row = data.iloc[0]
    return AccountFunds(
        acc_id=acc_id,
        trd_env=trd_env,
        currency=_text(row.get("currency")),
        cash=_num(row.get("cash")),
        total_assets=_num(row.get("total_assets")),
        securities_assets=_num(row.get("securities_assets")),
        market_val=_num(row.get("market_val")),
        available_funds=_num(row.get("available_funds")),
        frozen_cash=_num(row.get("frozen_cash")),
        power=_num(row.get("power")),
        unrealized_pl=_num(row.get("unrealized_pl")),
        realized_pl=_num(row.get("realized_pl")),
        initial_margin=_num(row.get("initial_margin")),
        maintenance_margin=_num(row.get("maintenance_margin")),
        risk_level=_text(row.get("risk_level")),
    )


def list_positions(
    client: OpendClient,
    trd_env: str,
    acc_id: int,
    code: str | None = None,
    currency: str = "USD",
) -> list[Position]:
    """Return open positions for ``acc_id`` (optionally filtered by ``code``)."""
    ret, data = client.trade_ctx.position_list_query(
        trd_env=trd_env, acc_id=acc_id, code=code or "", currency=currency
    )
    _require_ok("position_list_query", ret, data)
    positions = []
    for _, row in data.iterrows():
        positions.append(
            Position(
                code=_text(row.get("code")),
                stock_name=_text(row.get("stock_name")),
                position_market=_text(row.get("position_market")),
                qty=float(row.get("qty") or 0.0),
                can_sell_qty=float(row.get("can_sell_qty") or 0.0),
                cost_price=_num(row.get("cost_price")),
                average_cost=_num(row.get("average_cost")),
                nominal_price=_num(row.get("nominal_price")),
                market_val=_num(row.get("market_val")),
                pl_ratio=_num(row.get("pl_ratio")),
                pl_val=_num(row.get("pl_val")),
                unrealized_pl=_num(row.get("unrealized_pl")),
                realized_pl=_num(row.get("realized_pl")),
                currency=_text(row.get("currency")),
                position_side=_text(row.get("position_side")),
                strategy_type=_text(row.get("strategy_type")),
            )
        )
    return positions


def list_orders(
    client: OpendClient,
    trd_env: str,
    acc_id: int,
    history: bool = False,
    status_filter: list[str] | None = None,
    code: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> list[Order]:
    """Return current (or historical) orders for ``trd_env``."""
    statuses = status_filter or []
    if history:
        ret, data = client.trade_ctx.history_order_list_query(
            status_filter_list=statuses,
            code=code or "",
            start=start or "",
            end=end or "",
            trd_env=trd_env,
            acc_id=acc_id,
        )
        api = "history_order_list_query"
    else:
        ret, data = client.trade_ctx.order_list_query(
            status_filter_list=statuses,
            code=code or "",
            start=start or "",
            end=end or "",
            trd_env=trd_env,
            acc_id=acc_id,
        )
        api = "order_list_query"
    _require_ok(api, ret, data)
    orders = []
    for _, row in data.iterrows():
        orders.append(
            Order(
                code=_text(row.get("code")),
                stock_name=_text(row.get("stock_name")),
                order_market=_text(row.get("order_market")),
                trd_side=_text(row.get("trd_side")),
                order_type=_text(row.get("order_type")),
                order_status=_text(row.get("order_status")),
                order_id=_text(row.get("order_id")),
                qty=float(row.get("qty") or 0.0),
                price=float(row.get("price") or 0.0),
                dealt_qty=float(row.get("dealt_qty") or 0.0),
                dealt_avg_price=float(row.get("dealt_avg_price") or 0.0),
                create_time=_text(row.get("create_time")),
                updated_time=_text(row.get("updated_time")),
                time_in_force=_text(row.get("time_in_force")),
                currency=_text(row.get("currency")),
                remark=_text(row.get("remark")),
                last_err_msg=_text(row.get("last_err_msg")),
            )
        )
    return orders
