from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from mooc.domain.events import EventType
from mooc.domain.market import DataSource
from mooc.opend import events

OBSERVED = datetime(2026, 11, 8, 20, 0, tzinfo=UTC)


class _Ctx:
    def __init__(self, earnings: pd.DataFrame, economic: pd.DataFrame | None = None) -> None:
        self._earnings = earnings
        self._economic = economic if economic is not None else pd.DataFrame()
        self.earnings_calls: list[tuple[str, str]] = []

    def get_earnings_calendar(self, market, begin_date=None, end_date=None, **kwargs):
        self.earnings_calls.append((begin_date, end_date))
        return 0, self._earnings

    def get_economic_calendar(self, begin_date, end_date=None, next_page=None, **kwargs):
        if next_page is None:
            return 0, self._economic, "cursor", True
        return 0, pd.DataFrame(), None, False


class _Client:
    def __init__(self, ctx: _Ctx) -> None:
        self.quote_ctx = ctx


def test_earnings_calendar_splits_into_7_day_windows():
    earnings = pd.DataFrame(
        [
            {"security": "US.AAPL", "earnings_date": "2026-11-05", "pub_type": "BMO"},
            {"security": "US.MSFT", "earnings_date": "2026-11-12", "pub_type": "AMC"},
        ]
    )
    ctx = _Ctx(earnings)
    result = events.earnings_calendar(
        _Client(ctx), "US", begin="2026-11-01", end="2026-11-20", observed_at=OBSERVED
    )
    assert ctx.earnings_calls == [
        ("2026-11-01", "2026-11-07"),
        ("2026-11-08", "2026-11-14"),
        ("2026-11-15", "2026-11-20"),
    ]
    assert len(result) == 6  # 2 rows x 3 windows
    first = result[0]
    assert first.event_type is EventType.EARNINGS
    assert first.code == "US.AAPL"
    assert first.event_datetime == datetime(2026, 11, 5, tzinfo=UTC)
    assert first.source is DataSource.UNKNOWN


def test_economic_calendar_parses_epoch_and_pages():
    ts = int((OBSERVED + timedelta(days=1)).timestamp())
    economic = pd.DataFrame([{"title": "CPI", "timestamp": ts, "country": "US", "star": 3}])
    result = events.economic_calendar(
        _Client(_Ctx(pd.DataFrame(), economic)),
        begin="2026-11-09",
        end="2026-11-10",
        observed_at=OBSERVED,
    )
    assert len(result) == 1
    assert result[0].event_type is EventType.ECONOMIC
    assert result[0].event_datetime == datetime.fromtimestamp(ts, tz=UTC)
    assert result[0].code is None
