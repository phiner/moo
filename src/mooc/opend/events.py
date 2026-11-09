"""Event calendar access (read-only) built on ``moomoo-api``.

``get_earnings_calendar`` accepts at most a 7-day window, so requests are split
into <=7-day chunks. Calendar data is not a live quote, so events are recorded
with ``DataSource.UNKNOWN`` provenance rather than being labelled realtime.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from ..domain.events import Event, EventType
from ..domain.market import DataSource
from .client import OpendClient
from .values import require_ok as _require_ok

_MAX_WINDOW_DAYS = 7


def _dates(begin: str, end: str) -> list[date]:
    first = date.fromisoformat(begin)
    last = date.fromisoformat(end)
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def _chunks(days: list[date], size: int) -> list[tuple[date, date]]:
    return [
        (days[index], days[min(index + size - 1, len(days) - 1)])
        for index in range(0, len(days), size)
    ]


def _midnight(value) -> datetime:
    return datetime.combine(date.fromisoformat(str(value)[:10]), datetime.min.time(), tzinfo=UTC)


def earnings_calendar(
    client: OpendClient,
    market: str,
    *,
    begin: str,
    end: str,
    observed_at: datetime,
) -> list[Event]:
    """Return earnings events in ``[begin, end]`` (window split into <=7-day chunks)."""
    events: list[Event] = []
    for start, stop in _chunks(_dates(begin, end), _MAX_WINDOW_DAYS):
        ret, data = client.quote_ctx.get_earnings_calendar(
            market, begin_date=start.isoformat(), end_date=stop.isoformat()
        )
        _require_ok("get_earnings_calendar", ret, data)
        for _, row in data.iterrows():
            events.append(
                Event(
                    event_type=EventType.EARNINGS,
                    event_datetime=_midnight(row.get("earnings_date")),
                    observed_at=observed_at,
                    code=str(row.get("security") or "") or None,
                    source=DataSource.UNKNOWN,
                    payload=json.dumps(
                        {
                            "pub_type": row.get("pub_type"),
                            "period_text": row.get("period_text"),
                            "iv": row.get("iv"),
                            "iv_rank": row.get("iv_rank"),
                        },
                        default=str,
                    ),
                )
            )
    return events


def economic_calendar(
    client: OpendClient,
    *,
    begin: str,
    end: str,
    observed_at: datetime,
    market_list: list[str] | None = None,
    importance: str | None = None,
) -> list[Event]:
    """Return macro events in ``[begin, end]``, following the paging cursor."""
    events: list[Event] = []
    page = None
    while True:
        ret, data, page, _has_more = client.quote_ctx.get_economic_calendar(
            begin_date=begin,
            end_date=end,
            market_list=market_list,
            importance=importance,
            next_page=page,
        )
        _require_ok("get_economic_calendar", ret, data)
        for _, row in data.iterrows():
            events.append(
                Event(
                    event_type=EventType.ECONOMIC,
                    event_datetime=datetime.fromtimestamp(float(row.get("timestamp") or 0), tz=UTC),
                    observed_at=observed_at,
                    source=DataSource.UNKNOWN,
                    payload=json.dumps(
                        {
                            "title": row.get("title"),
                            "country": row.get("country"),
                            "star": row.get("star"),
                        },
                        default=str,
                    ),
                )
            )
        if page is None:
            break
    return events
