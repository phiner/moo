from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from mooc.domain.market import DataSource
from mooc.opend import quote

# 2026-11-06 15:00 US/Eastern == 20:00 UTC (EST, UTC-5).
NOW = datetime(2026, 11, 6, 20, 30, tzinfo=UTC)


class _Ctx:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def get_market_snapshot(self, codes):
        return 0, self._frame[self._frame["code"].isin(codes)]


class _Client:
    def __init__(self, ctx: _Ctx) -> None:
        self.quote_ctx = ctx


def _client(frame: pd.DataFrame) -> _Client:
    return _Client(_Ctx(frame))


def test_stock_snapshot_parses_eastern_update_time_to_utc():
    frame = pd.DataFrame(
        [
            {
                "code": "US.AAPL",
                "update_time": "2026-11-06 15:00:00",
                "last_price": 275.0,
                "bid_price": 274.9,
                "ask_price": 275.1,
                "volume": 1234,
            }
        ]
    )
    snap = quote.stock_snapshot(_client(frame), ["US.AAPL"], now=NOW, max_age_seconds=3600)[
        "US.AAPL"
    ]
    assert snap.quality.source is DataSource.REALTIME
    assert snap.quality.observed_at == datetime(2026, 11, 6, 20, 0, tzinfo=UTC)
    assert snap.quality.is_stale is False
    assert (snap.last, snap.bid, snap.ask, snap.volume) == (275.0, 274.9, 275.1, 1234)


def test_stock_snapshot_flags_stale_and_missing_update_time():
    stale = pd.DataFrame(
        [
            {
                "code": "US.AAPL",
                "update_time": "2026-11-06 10:00:00",
                "last_price": 275.0,
                "bid_price": 274.9,
                "ask_price": 275.1,
                "volume": 1,
            }
        ]
    )
    snap = quote.stock_snapshot(_client(stale), ["US.AAPL"], now=NOW, max_age_seconds=3600)[
        "US.AAPL"
    ]
    assert snap.quality.is_stale is True

    missing = pd.DataFrame(
        [
            {
                "code": "US.AAPL",
                "update_time": None,
                "last_price": 275.0,
                "bid_price": None,
                "ask_price": None,
                "volume": None,
            }
        ]
    )
    snap = quote.stock_snapshot(_client(missing), ["US.AAPL"], now=NOW, max_age_seconds=3600)[
        "US.AAPL"
    ]
    assert snap.quality.missing_fields == ("update_time",)
    assert snap.quality.observed_at == NOW
