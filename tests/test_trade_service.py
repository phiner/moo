from __future__ import annotations

import pandas as pd

from mooc.config import AppConfig
from mooc.ipc import protocol
from mooc.services.trade import TradeService

TRADING = AppConfig().trading


class _Ctx:
    def __init__(self, accounts: pd.DataFrame | None = None) -> None:
        self._accounts = accounts if accounts is not None else pd.DataFrame()

    def get_acc_list(self):
        return 0, self._accounts

    def accinfo_query(self, **kwargs):
        return 0, pd.DataFrame()

    def position_list_query(self, **kwargs):
        return 0, pd.DataFrame()

    def order_list_query(self, **kwargs):
        return 0, pd.DataFrame()

    def history_order_list_query(self, **kwargs):
        return 0, pd.DataFrame()


class _Client:
    def __init__(self, ctx: _Ctx) -> None:
        self._ctx = ctx

    @property
    def trade_ctx(self):
        return self._ctx


class _ErrCtx:
    def get_acc_list(self):
        return -1, "boom"


def test_dispatch_accounts():
    accounts = pd.DataFrame(
        [
            {
                "acc_id": 7,
                "trd_env": "SIMULATE",
                "acc_type": "CASH",
                "card_num": "1",
                "security_firm": "FUTUSECURITIES",
                "sim_acc_type": "STOCK",
                "acc_status": "ACTIVE",
                "acc_role": "MASTER",
                "trdmarket_auth": ["US"],
            },
        ]
    )
    service = TradeService(_Client(_Ctx(accounts)), TRADING)
    response = service.dispatch(protocol.GetAccounts(request_id=3))
    assert response.kind == "AccountsResult"
    assert response.request_id == 3
    assert response.accounts[0].acc_id == 7


def test_default_env_is_simulate():
    service = TradeService(_Client(_Ctx()), TRADING)
    response = service.dispatch(protocol.GetFunds())
    assert response.kind == "FundsResult"
    assert response.funds is None


def test_disallowed_env_is_rejected():
    api = _Client(_ErrCtx())
    service = TradeService(api, TRADING)
    response = service.dispatch(protocol.GetAccounts(trd_env="REAL"))
    assert response.kind == "Error"
    assert "not allowed" in response.message


def test_sdk_error_becomes_error_result():
    api = _Client(_ErrCtx())
    service = TradeService(api, TRADING)
    response = service.dispatch(protocol.GetAccounts())
    assert response.kind == "Error"
    assert "get_acc_list" in response.message


def test_unknown_request_kind_is_an_error():
    service = TradeService(_Client(_Ctx()), TRADING)
    response = service.dispatch(protocol.GetOptionExpirations(underlying="US.AAPL"))
    assert response.kind == "Error"
