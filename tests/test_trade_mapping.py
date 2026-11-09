from __future__ import annotations

import pandas as pd

from mooc.opend import trade


class _FakeCtx:
    def __init__(self, **frames: pd.DataFrame) -> None:
        self._frames = frames
        self.calls = {}

    def get_acc_list(self):
        return 0, self._frames["accounts"]

    def accinfo_query(self, **kwargs):
        self.calls["funds"] = kwargs
        return 0, self._frames["funds"]

    def position_list_query(self, **kwargs):
        self.calls["positions"] = kwargs
        return 0, self._frames["positions"]

    def order_list_query(self, **kwargs):
        self.calls["orders"] = kwargs
        return 0, self._frames["orders"]

    def history_order_list_query(self, **kwargs):
        self.calls["history"] = kwargs
        return 0, self._frames["history"]


class _FakeClient:
    def __init__(self, ctx: _FakeCtx) -> None:
        self._ctx = ctx

    @property
    def trade_ctx(self):
        return self._ctx


def _client(**frames: pd.DataFrame) -> _FakeClient:
    return _FakeClient(_FakeCtx(**frames))


def test_list_accounts_filters_by_env():
    accounts = pd.DataFrame(
        [
            {
                "acc_id": 1,
                "trd_env": "SIMULATE",
                "acc_type": "CASH",
                "card_num": "1",
                "security_firm": "FUTUSECURITIES",
                "sim_acc_type": "STOCK",
                "acc_status": "ACTIVE",
                "acc_role": "MASTER",
                "trdmarket_auth": ["US"],
            },
            {
                "acc_id": 2,
                "trd_env": "REAL",
                "acc_type": "MARGIN",
                "card_num": "2",
                "security_firm": "FUTUSECURITIES",
                "sim_acc_type": "N/A",
                "acc_status": "ACTIVE",
                "acc_role": "MASTER",
                "trdmarket_auth": ["US"],
            },
        ]
    )
    result = trade.list_accounts(_client(accounts=accounts), "SIMULATE")
    assert [a.acc_id for a in result] == [1]
    assert result[0].trdmarket_auth == ["US"]


def test_get_funds_maps_fields_and_missing_markers():
    funds = pd.DataFrame(
        [
            {
                "currency": "USD",
                "cash": 1000.0,
                "total_assets": "N/A",
                "securities_assets": 250.0,
                "market_val": 250.0,
                "available_funds": 900.0,
                "frozen_cash": 0.0,
                "power": 1800.0,
                "unrealized_pl": -12.5,
                "realized_pl": 3.0,
                "initial_margin": 0.0,
                "maintenance_margin": 0.0,
                "risk_level": "SAFE",
            }
        ]
    )
    client = _client(funds=funds)
    result = trade.get_funds(client, "SIMULATE", 42)
    assert result is not None
    assert result.cash == 1000.0
    assert result.total_assets is None
    assert result.unrealized_pl == -12.5
    assert result.risk_level == "SAFE"
    assert result.acc_id == 42
    assert client.trade_ctx.calls["funds"]["acc_id"] == 42


def test_get_funds_empty_returns_none():
    assert trade.get_funds(_client(funds=pd.DataFrame()), "SIMULATE", 42) is None


def test_list_positions_maps_fields():
    positions = pd.DataFrame(
        [
            {
                "code": "US.AAPL261118C270000",
                "stock_name": "AAPL 11/18 CALL 270",
                "position_market": "US",
                "qty": 2,
                "can_sell_qty": 2,
                "cost_price": "N/A",
                "average_cost": 6.5,
                "nominal_price": 7.1,
                "market_val": 1420.0,
                "pl_ratio": 9.2,
                "pl_val": 120.0,
                "unrealized_pl": 120.0,
                "realized_pl": 0.0,
                "currency": "USD",
                "position_side": "LONG",
                "strategy_type": "N/A",
            }
        ]
    )
    client = _client(positions=positions)
    position = trade.list_positions(client, "SIMULATE", 42)[0]
    assert position.qty == 2.0
    assert position.cost_price is None
    assert position.average_cost == 6.5
    assert position.position_side == "LONG"
    assert client.trade_ctx.calls["positions"]["acc_id"] == 42


def test_list_orders_current_and_history():
    order = pd.DataFrame(
        [
            {
                "code": "US.AAPL261118C270000",
                "stock_name": "AAPL 11/18 CALL 270",
                "order_market": "US",
                "trd_side": "BUY",
                "order_type": "NORMAL",
                "order_status": "SUBMITTED",
                "order_id": "1001",
                "qty": 1.0,
                "price": 7.0,
                "dealt_qty": 0.0,
                "dealt_avg_price": 0.0,
                "create_time": "2026-11-08 09:30:00",
                "updated_time": "2026-11-08 09:30:00",
                "time_in_force": "DAY",
                "currency": "USD",
                "remark": "",
                "last_err_msg": "",
            }
        ]
    )
    current_client = _client(orders=order)
    current = trade.list_orders(current_client, "SIMULATE", 42)
    assert current[0].order_id == "1001"
    assert current[0].trd_side == "BUY"
    assert current_client.trade_ctx.calls["orders"]["acc_id"] == 42

    history_client = _client(history=order)
    history = trade.list_orders(history_client, "SIMULATE", 42, history=True)
    assert history[0].order_status == "SUBMITTED"
    assert history_client.trade_ctx.calls["history"]["acc_id"] == 42
