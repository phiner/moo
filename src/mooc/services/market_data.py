"""Market data service: snapshots, volatility, and events with provenance.

Maps IPC requests to the ``opend`` access layer, applies the configured
freshness thresholds, and returns DTOs that always carry ``quality`` so callers
can tell stale/missing data from fresh. SDK calls are serialized through a lock
(one context, no documented concurrency guarantee).
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from datetime import UTC, date, datetime, timedelta

from ..config import AppConfig
from ..domain.events import Event
from ..domain.market import StockQuote
from ..domain.rules import StrategyRule
from ..ipc import protocol
from ..opend import events as events_api
from ..opend import quote as quote_api
from ..opend import volatility as vol_api
from ..opend.client import OpendClient
from ..opend.errors import MoocError
from ..storage import db as storage_db
from ..storage import repo as storage_repo
from .analyze import analyze_symbol
from .journal import report as journal_report
from .rules import load_rules
from .volatility import summarize

logger = logging.getLogger(__name__)

_DEFAULT_EVENT_WINDOW_DAYS = 7


class MarketDataService:
    def __init__(self, client: OpendClient, config: AppConfig | None = None) -> None:
        self._client = client
        self._config = config or AppConfig()
        self._lock = threading.Lock()
        self._rules = self._load_rules()

    def _load_rules(self) -> list[StrategyRule]:
        try:
            return load_rules(self._config.rules.path)
        except MoocError as exc:
            logger.warning("no strategy rules loaded: %s", exc)
            return []

    # -- request dispatch --------------------------------------------------
    def dispatch(self, request) -> protocol.Response:
        """Route one request to a handler. Never raises; errors become ``ErrorResult``."""
        request_id = getattr(request, "request_id", None)
        try:
            with self._lock:
                return self._dispatch_locked(request, request_id)
        except MoocError as exc:
            return protocol.ErrorResult(request_id=request_id, message=str(exc))
        except Exception as exc:  # noqa: BLE001 - boundary: never kill the loop
            return protocol.ErrorResult(request_id=request_id, message=f"internal error: {exc}")

    def _dispatch_locked(self, request, request_id: int | None) -> protocol.Response:
        if isinstance(request, protocol.GetStockSnapshot):
            return self._snapshot(request)
        if isinstance(request, protocol.GetVolatility):
            return self._volatility(request)
        if isinstance(request, protocol.GetEvents):
            return self._events(request)
        if isinstance(request, protocol.GetAnalysis):
            return self._analysis(request)
        if isinstance(request, protocol.GetJournal):
            return self._journal(request)
        return protocol.ErrorResult(request_id=request_id, message="unknown market request kind")

    # -- handlers ----------------------------------------------------------
    def _snapshot(self, request: protocol.GetStockSnapshot) -> protocol.Response:
        now = datetime.now(UTC)
        max_age = self._config.data_quality.realtime_max_age_sec
        quotes = quote_api.stock_snapshot(
            self._client, request.codes, now=now, max_age_seconds=max_age
        )
        return protocol.StockSnapshotResult(
            request_id=request.request_id,
            quotes=[_snapshot_dto(quote) for quote in quotes.values()],
        )

    def _volatility(self, request: protocol.GetVolatility) -> protocol.Response:
        end = date.today()
        begin = end - timedelta(days=request.history_days)
        points = vol_api.his_volatility(
            self._client, request.code, begin=begin.isoformat(), end=end.isoformat()
        )
        summary = summarize(points, lookback=request.lookback)
        days = [point.day for point in points]
        item = protocol.VolatilityDTO(
            code=request.code,
            iv=summary.iv,
            hv=summary.hv,
            iv_rank=summary.iv_rank,
            iv_percentile=summary.iv_percentile,
            iv_hv_diff=summary.iv_hv_diff,
            sample_size=len(points),
            first_day=days[0].isoformat() if days else None,
            last_day=days[-1].isoformat() if days else None,
        )
        return protocol.VolatilityResult(request_id=request.request_id, item=item)

    def _events(self, request: protocol.GetEvents) -> protocol.Response:
        now = datetime.now(UTC)
        begin = request.begin or date.today().isoformat()
        end = (
            request.end
            or (date.fromisoformat(begin) + timedelta(days=_DEFAULT_EVENT_WINDOW_DAYS)).isoformat()
        )
        collected: list[Event] = []
        if request.include_earnings:
            collected += events_api.earnings_calendar(
                self._client, request.market, begin=begin, end=end, observed_at=now
            )
        if request.include_economic:
            collected += events_api.economic_calendar(
                self._client, begin=begin, end=end, observed_at=now
            )
        collected.sort(key=lambda event: event.event_datetime)
        return protocol.EventsResult(
            request_id=request.request_id,
            events=[_event_dto(event) for event in collected],
        )

    def _analysis(self, request: protocol.GetAnalysis) -> protocol.Response:
        output = analyze_symbol(
            self._client,
            request.code,
            rules=self._rules,
            config=self._config,
        )
        return protocol.AnalysisResult(request_id=request.request_id, output=output.to_dict())

    def _journal(self, request: protocol.GetJournal) -> protocol.Response:
        conn = storage_db.open_db(self._config.storage.path)
        try:
            entries = storage_repo.journal_entries(conn, symbol=request.symbol)
        finally:
            conn.close()
        return protocol.JournalResult(
            request_id=request.request_id,
            report=dataclasses.asdict(journal_report(entries)),
        )


def _snapshot_dto(quote: StockQuote) -> protocol.StockSnapshotDTO:
    return protocol.StockSnapshotDTO(
        code=quote.code,
        last=quote.last,
        bid=quote.bid,
        ask=quote.ask,
        volume=quote.volume,
        update_time=quote.update_time.isoformat() if quote.update_time else None,
        quality=protocol.QualityDTO(
            source=quote.quality.source.value,
            observed_at=quote.quality.observed_at.isoformat(),
            is_stale=quote.quality.is_stale,
            missing_fields=list(quote.quality.missing_fields),
        ),
    )


def _event_dto(event: Event) -> protocol.EventDTO:
    return protocol.EventDTO(
        event_type=event.event_type.value,
        event_datetime=event.event_datetime.isoformat(),
        code=event.code,
        status=event.status,
        source=event.source.value,
        payload=event.payload,
    )
