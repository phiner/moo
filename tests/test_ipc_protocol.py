from __future__ import annotations

import pytest
from pydantic import ValidationError

from mooc.ipc import protocol


def test_request_roundtrip():
    req = protocol.GetOptionExpirations(underlying="US.AAPL", request_id=7)
    assert protocol.decode_request(protocol.encode(req)) == req


def test_response_roundtrip():
    resp = protocol.OptionExpirationsResult(request_id=1, dates=["2026-11-18"])
    assert protocol.decode_response(protocol.encode(resp)) == resp


@pytest.mark.parametrize(
    "bad",
    [
        {"code": "X", "action": "HOLD", "quantity": 1},
        {"code": "X", "action": "BUY", "quantity": 0},
        {"code": "X", "action": "BUY", "quantity": -1},
        {"code": "", "action": "BUY", "quantity": 1},
    ],
)
def test_leg_validation_rejects(bad):
    with pytest.raises(ValidationError):
        protocol.Leg(**bad)


def test_combo_leg_count_bounds():
    with pytest.raises(ValidationError):
        protocol.GetComboAnalysis(legs=[])
    too_many = [{"code": f"US.X{index}"} for index in range(protocol.MAX_LEGS + 1)]
    with pytest.raises(ValidationError):
        protocol.GetComboAnalysis(legs=too_many)


def test_option_type_is_constrained():
    with pytest.raises(ValidationError):
        protocol.GetOptionChain(underlying="US.AAPL", option_type="BOTH")


def test_encode_enforces_frame_limit(monkeypatch):
    monkeypatch.setattr(protocol, "MAX_FRAME_BYTES", 10)
    with pytest.raises(ValueError):
        protocol.encode(protocol.GetOptionExpirations(underlying="US.AAPL"))


def test_trade_request_roundtrip():
    req = protocol.GetOrders(
        trd_env="SIMULATE", history=True, status_filter=["FILLED_ALL"], code="US.AAPL"
    )
    assert protocol.decode_request(protocol.encode(req)) == req


def test_trade_response_roundtrip():
    resp = protocol.AccountsResult(
        request_id=2,
        accounts=[
            protocol.AccountDTO(
                acc_id=1,
                trd_env="SIMULATE",
                acc_type="CASH",
                card_num="1",
                security_firm="FUTUSECURITIES",
                sim_acc_type="STOCK",
                acc_status="ACTIVE",
                acc_role="MASTER",
                trdmarket_auth=["US"],
            )
        ],
    )
    assert protocol.decode_response(protocol.encode(resp)) == resp


def test_invalid_trd_env_rejected():
    with pytest.raises(ValidationError):
        protocol.GetAccounts(trd_env="LIVE")


def test_trade_requests_cover_all_kinds():
    kinds = {model.model_fields["kind"].default for model in protocol.TRADE_REQUESTS}
    assert kinds == {"GetAccounts", "GetFunds", "GetPositions", "GetOrders"}
