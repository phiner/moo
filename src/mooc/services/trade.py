"""Trade service: maps read-only IPC requests to SDK calls and domain -> IPC DTOs.

Every request resolves its trade environment through the local safety policy, so
a disallowed environment (e.g. REAL when the policy is SIMULATE-only) is
rejected before any SDK call. SDK calls are serialized through one lock.
"""

from __future__ import annotations

import threading

from ..config import TradingConfig
from ..ipc import protocol
from ..opend import trade
from ..opend.client import OpendClient
from ..opend.errors import MoocError
from ..policy import resolve_trd_env


class TradeService:
    def __init__(self, client: OpendClient, trading: TradingConfig) -> None:
        self._client = client
        self._trading = trading
        self._lock = threading.Lock()

    # -- request dispatch --------------------------------------------------
    def dispatch(self, request) -> protocol.Response:
        """Route one trade request to a handler. Never raises; errors become errors."""
        request_id = getattr(request, "request_id", None)
        try:
            with self._lock:
                return self._dispatch_locked(request, request_id)
        except MoocError as exc:
            return protocol.ErrorResult(request_id=request_id, message=str(exc))
        except Exception as exc:  # noqa: BLE001 - boundary: never kill the loop
            return protocol.ErrorResult(request_id=request_id, message=f"internal error: {exc}")

    def _dispatch_locked(self, request, request_id: int | None) -> protocol.Response:
        if isinstance(request, protocol.GetAccounts):
            return self._accounts(request)
        if isinstance(request, protocol.GetFunds):
            return self._funds(request)
        if isinstance(request, protocol.GetPositions):
            return self._positions(request)
        if isinstance(request, protocol.GetOrders):
            return self._orders(request)
        return protocol.ErrorResult(request_id=request_id, message="unknown trade request kind")

    def _currency(self, requested: str | None) -> str:
        return (requested or self._trading.default_currency).upper()

    # -- handlers ----------------------------------------------------------
    def _accounts(self, request: protocol.GetAccounts) -> protocol.Response:
        trd_env = resolve_trd_env(request.trd_env, self._trading)
        accounts = trade.list_accounts(self._client, trd_env)
        return protocol.AccountsResult(
            request_id=request.request_id,
            accounts=[
                protocol.AccountDTO(
                    acc_id=a.acc_id,
                    trd_env=a.trd_env,
                    acc_type=a.acc_type,
                    card_num=a.card_num,
                    security_firm=a.security_firm,
                    sim_acc_type=a.sim_acc_type,
                    acc_status=a.acc_status,
                    acc_role=a.acc_role,
                    trdmarket_auth=a.trdmarket_auth,
                )
                for a in accounts
            ],
        )

    def _funds(self, request: protocol.GetFunds) -> protocol.Response:
        trd_env = resolve_trd_env(request.trd_env, self._trading)
        funds = trade.get_funds(self._client, trd_env, currency=self._currency(request.currency))
        dto = None
        if funds is not None:
            dto = protocol.FundsDTO(
                trd_env=funds.trd_env,
                currency=funds.currency,
                cash=funds.cash,
                total_assets=funds.total_assets,
                securities_assets=funds.securities_assets,
                market_val=funds.market_val,
                available_funds=funds.available_funds,
                frozen_cash=funds.frozen_cash,
                power=funds.power,
                unrealized_pl=funds.unrealized_pl,
                realized_pl=funds.realized_pl,
                initial_margin=funds.initial_margin,
                maintenance_margin=funds.maintenance_margin,
                risk_level=funds.risk_level,
            )
        return protocol.FundsResult(request_id=request.request_id, funds=dto)

    def _positions(self, request: protocol.GetPositions) -> protocol.Response:
        trd_env = resolve_trd_env(request.trd_env, self._trading)
        positions = trade.list_positions(
            self._client, trd_env, code=request.code, currency=self._currency(request.currency)
        )
        return protocol.PositionsResult(
            request_id=request.request_id,
            positions=[
                protocol.PositionDTO(
                    code=p.code,
                    stock_name=p.stock_name,
                    position_market=p.position_market,
                    qty=p.qty,
                    can_sell_qty=p.can_sell_qty,
                    cost_price=p.cost_price,
                    average_cost=p.average_cost,
                    nominal_price=p.nominal_price,
                    market_val=p.market_val,
                    pl_ratio=p.pl_ratio,
                    pl_val=p.pl_val,
                    unrealized_pl=p.unrealized_pl,
                    realized_pl=p.realized_pl,
                    currency=p.currency,
                    position_side=p.position_side,
                    strategy_type=p.strategy_type,
                )
                for p in positions
            ],
        )

    def _orders(self, request: protocol.GetOrders) -> protocol.Response:
        trd_env = resolve_trd_env(request.trd_env, self._trading)
        orders = trade.list_orders(
            self._client,
            trd_env,
            history=request.history,
            status_filter=request.status_filter,
            code=request.code,
            start=request.start,
            end=request.end,
        )
        return protocol.OrdersResult(
            request_id=request.request_id,
            orders=[
                protocol.OrderDTO(
                    code=o.code,
                    stock_name=o.stock_name,
                    order_market=o.order_market,
                    trd_side=o.trd_side,
                    order_type=o.order_type,
                    order_status=o.order_status,
                    order_id=o.order_id,
                    qty=o.qty,
                    price=o.price,
                    dealt_qty=o.dealt_qty,
                    dealt_avg_price=o.dealt_avg_price,
                    create_time=o.create_time,
                    updated_time=o.updated_time,
                    time_in_force=o.time_in_force,
                    currency=o.currency,
                    remark=o.remark,
                    last_err_msg=o.last_err_msg,
                )
                for o in orders
            ],
        )
