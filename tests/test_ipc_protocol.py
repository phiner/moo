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
        acc_id=42,
        trd_env="SIMULATE",
        history=True,
        status_filter=["FILLED_ALL"],
        code="US.AAPL",
    )
    assert protocol.decode_request(protocol.encode(req)) == req


@pytest.mark.parametrize(
    "request_type", [protocol.GetFunds, protocol.GetPositions, protocol.GetOrders]
)
@pytest.mark.parametrize("acc_id", [None, 0, -1])
def test_trade_requests_reject_missing_or_nonpositive_account(request_type, acc_id):
    if acc_id is None:
        with pytest.raises(ValidationError):
            request_type()
    else:
        with pytest.raises(ValidationError):
            request_type(acc_id=acc_id)


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

    empty_positions = protocol.PositionsResult(request_id=3, acc_id=42, positions=[])
    assert protocol.decode_response(protocol.encode(empty_positions)) == empty_positions


def test_invalid_trd_env_rejected():
    with pytest.raises(ValidationError):
        protocol.GetAccounts(trd_env="LIVE")


def test_trade_requests_cover_all_kinds():
    kinds = {model.model_fields["kind"].default for model in protocol.TRADE_REQUESTS}
    assert kinds == {"GetAccounts", "GetFunds", "GetPositions", "GetOrders"}


def test_watchlist_request_roundtrip():
    req = protocol.GetWatchlistSummary(group_name="Mine", limit=10, request_id=4)
    assert protocol.decode_request(protocol.encode(req)) == req


@pytest.mark.parametrize(
    "bad",
    [{"group_name": ""}, {"group_name": "x", "limit": 0}, {"group_name": "x", "limit": 500}],
)
def test_watchlist_summary_validation(bad):
    with pytest.raises(ValidationError):
        protocol.GetWatchlistSummary(**bad)


def test_market_requests_cover_all_kinds():
    kinds = {model.model_fields["kind"].default for model in protocol.MARKET_REQUESTS}
    assert kinds == {"GetStockSnapshot", "GetVolatility", "GetEvents", "GetAnalysis"}


def test_analysis_roundtrip():
    req = protocol.GetAnalysis(code="US.AAPL", request_id=11)
    assert protocol.decode_request(protocol.encode(req)) == req

    resp = protocol.AnalysisResult(
        request_id=11,
        output={"symbol": "US.AAPL", "trade_status": "REJECTED", "strategy": {"type": "x"}},
    )
    assert protocol.decode_response(protocol.encode(resp)) == resp


def test_market_request_roundtrip_and_bounds():
    req = protocol.GetStockSnapshot(codes=["US.AAPL", "US.MSFT"], request_id=9)
    assert protocol.decode_request(protocol.encode(req)) == req

    with pytest.raises(ValidationError):
        protocol.GetStockSnapshot(codes=[])
    with pytest.raises(ValidationError):
        protocol.GetVolatility(code="US.AAPL", lookback=0)
    with pytest.raises(ValidationError):
        protocol.GetVolatility(code="US.AAPL", history_days=999)


def test_market_response_roundtrip():
    resp = protocol.StockSnapshotResult(
        request_id=1,
        quotes=[
            protocol.StockSnapshotDTO(
                code="US.AAPL",
                last=275.0,
                bid=274.9,
                ask=275.1,
                volume=10,
                update_time="2026-11-06T20:00:00+00:00",
                quality=protocol.QualityDTO(
                    source="realtime",
                    observed_at="2026-11-06T20:00:00+00:00",
                    is_stale=False,
                    missing_fields=[],
                ),
            )
        ],
    )
    assert protocol.decode_response(protocol.encode(resp)) == resp

    vol = protocol.VolatilityResult(
        request_id=2,
        item=protocol.VolatilityDTO(
            code="US.AAPL",
            iv=40.0,
            hv=25.0,
            iv_rank=100.0,
            iv_percentile=50.0,
            iv_hv_diff=15.0,
            sample_size=2,
            first_day="2026-11-05",
            last_day="2026-11-06",
        ),
    )
    assert protocol.decode_response(protocol.encode(vol)) == vol


def test_watchlist_summary_response_roundtrip():
    resp = protocol.WatchlistSummaryResult(
        request_id=1,
        group_name="Mine",
        items=[
            protocol.UnderlyingSummaryDTO(
                code="US.AAPL",
                name="Apple",
                last_price=275.0,
                expiry="2099-01-15",
                atm_strike=275.0,
                call_bid=6.4,
                call_ask=13.4,
                put_bid=5.0,
                put_ask=6.0,
            )
        ],
    )
    assert protocol.decode_response(protocol.encode(resp)) == resp
