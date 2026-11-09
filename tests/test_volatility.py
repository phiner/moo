from __future__ import annotations

from datetime import date

import pandas as pd

from mooc.domain.market import VolatilityPoint
from mooc.opend import volatility
from mooc.services import volatility as vol_svc


def test_iv_rank_and_percentile():
    values = [10.0, 20.0, 30.0, 40.0]
    assert vol_svc.iv_rank(values, 25.0) == (25.0 - 10.0) / 30.0 * 100.0
    assert vol_svc.iv_rank(values, 10.0) == 0.0
    assert vol_svc.iv_rank(values, 40.0) == 100.0
    assert vol_svc.iv_percentile(values, 25.0) == 50.0
    assert vol_svc.iv_percentile([], 25.0) == 0.0


def test_iv_rank_flat_series_is_zero():
    assert vol_svc.iv_rank([30.0, 30.0], 30.0) == 0.0


def test_summarize_empty_and_latest():
    assert vol_svc.summarize([]) == vol_svc.VolatilitySummary(None, None, None, None, None)

    points = [
        VolatilityPoint(day=date(2026, 11, 6), iv=None, hv=None),
        VolatilityPoint(day=date(2026, 11, 7), iv=20.0, hv=15.0),
        VolatilityPoint(day=date(2026, 11, 8), iv=40.0, hv=25.0),
    ]
    summary = vol_svc.summarize(points)
    assert summary.iv == 40.0
    assert summary.hv == 25.0
    assert summary.iv_rank == 100.0
    assert summary.iv_percentile == 50.0
    assert summary.iv_hv_diff == 15.0


class _Ctx:
    def __init__(self, pages: list[tuple[pd.DataFrame, str | None]]) -> None:
        self._pages = pages
        self.calls = 0

    def get_option_underlying_his_volatility(self, code, **kwargs):
        frame, next_page = self._pages[self.calls]
        self.calls += 1
        return 0, frame, next_page


class _Client:
    def __init__(self, ctx: _Ctx) -> None:
        self.quote_ctx = ctx


def test_his_volatility_follows_pagination_and_sorts():
    page1 = pd.DataFrame(
        [
            {"time": "2026-11-06", "iv": 30.0, "hv": 20.0, "underlying_price": 275.0},
            {"time": "2026-11-05", "iv": 28.0, "hv": 19.0, "underlying_price": 273.0},
        ]
    )
    page2 = pd.DataFrame(
        [{"time": "2026-11-04", "iv": 27.0, "hv": 18.0, "underlying_price": 271.0}]
    )
    client = _Client(_Ctx([(page1, "cursor"), (page2, None)]))
    points = volatility.his_volatility(client, "US.AAPL", begin="2026-11-01", end="2026-11-08")
    assert [p.day for p in points] == [date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6)]
    assert points[-1].iv == 30.0
    assert client.quote_ctx.calls == 2
