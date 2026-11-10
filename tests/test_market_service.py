from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from mooc.config import AppConfig
from mooc.ipc import protocol
from mooc.services.market_data import MarketDataService

_EASTERN = ZoneInfo("America/New_York")


class _Ctx:
    def __init__(self, **frames: pd.DataFrame) -> None:
        self._frames = frames

    def get_market_snapshot(self, codes):
        return 0, self._frames["snapshot"]

    def get_option_underlying_his_volatility(self, code, **kwargs):
        return 0, self._frames["volatility"], None

    def get_earnings_calendar(self, market, begin_date=None, end_date=None, **kwargs):
        return 0, self._frames["earnings"]


class _Client:
    def __init__(self, ctx: _Ctx) -> None:
        self.quote_ctx = ctx


class _ErrCtx:
    def get_market_snapshot(self, codes):
        return -1, "boom"


class _ErrClient:
    @property
    def quote_ctx(self):
        return _ErrCtx()


def _recent_update_time() -> str:
    return datetime.now(_EASTERN).strftime("%Y-%m-%d %H:%M:%S")


def test_snapshot_reports_fresh_and_stale():
    snapshot = pd.DataFrame(
        [
            {
                "code": "US.AAPL",
                "update_time": _recent_update_time(),
                "last_price": 275.0,
                "bid_price": 274.9,
                "ask_price": 275.1,
                "volume": 10,
            },
            {
                "code": "US.OLD",
                "update_time": "2020-01-02 15:00:00",
                "last_price": 5.0,
                "bid_price": 4.9,
                "ask_price": 5.1,
                "volume": 1,
            },
        ]
    )
    service = MarketDataService(_Client(_Ctx(snapshot=snapshot)), AppConfig())
    response = service.dispatch(protocol.GetStockSnapshot(codes=["US.AAPL", "US.OLD"]))
    assert response.kind == "StockSnapshotResult"
    by_code = {quote.code: quote for quote in response.quotes}
    assert by_code["US.AAPL"].quality.is_stale is False
    assert by_code["US.AAPL"].quality.source == "realtime"
    assert by_code["US.OLD"].quality.is_stale is True


def test_volatility_summarizes_series():
    volatility = pd.DataFrame(
        [
            {"time": "2026-11-05", "iv": 20.0, "hv": 15.0, "underlying_price": 270.0},
            {"time": "2026-11-06", "iv": 40.0, "hv": 25.0, "underlying_price": 275.0},
        ]
    )
    service = MarketDataService(_Client(_Ctx(volatility=volatility)), AppConfig())
    response = service.dispatch(protocol.GetVolatility(code="US.AAPL", lookback=252))
    assert response.kind == "VolatilityResult"
    assert response.item is not None
    assert response.item.iv == 40.0
    assert response.item.iv_rank == 100.0
    assert response.item.sample_size == 2
    assert response.item.first_day == "2026-11-05"


def test_events_returns_sorted_earnings():
    earnings = pd.DataFrame(
        [
            {"security": "US.MSFT", "earnings_date": "2026-11-12", "pub_type": "AMC"},
            {"security": "US.AAPL", "earnings_date": "2026-11-05", "pub_type": "BMO"},
        ]
    )
    service = MarketDataService(_Client(_Ctx(earnings=earnings)), AppConfig())
    response = service.dispatch(protocol.GetEvents(begin="2026-11-01", end="2026-11-07"))
    assert response.kind == "EventsResult"
    assert [event.code for event in response.events] == ["US.AAPL", "US.MSFT"]
    assert response.events[0].event_type == "earnings"


def test_sdk_error_becomes_error_result():
    service = MarketDataService(_ErrClient(), AppConfig())
    response = service.dispatch(protocol.GetStockSnapshot(codes=["US.AAPL"]))
    assert response.kind == "Error"
    assert "get_market_snapshot" in response.message


def test_unknown_request_kind_is_an_error():
    service = MarketDataService(_Client(_Ctx(snapshot=pd.DataFrame())), AppConfig())
    response = service.dispatch(protocol.GetOptionExpirations(underlying="US.AAPL"))
    assert response.kind == "Error"
