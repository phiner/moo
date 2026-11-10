from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from mooc.domain.events import Event, EventType
from mooc.domain.market import DataSource, OptionSnapshot, StockQuote, quality_for
from mooc.domain.options import OptionContract, OptionType
from mooc.storage import db, repo

NOW = datetime(2026, 11, 8, 20, 0, tzinfo=UTC)


def _db(tmp_path):
    return db.open_db(tmp_path / "mooc.db")


def _stock(code: str, *, source=DataSource.REALTIME, observed=NOW, last=100.0) -> StockQuote:
    return StockQuote(
        code=code,
        quality=quality_for(source, observed, now=NOW, max_age_seconds=60),
        last=last,
        bid=last - 0.1,
        ask=last + 0.1,
        volume=1000,
    )


def test_migrate_is_idempotent_and_stamps_version(tmp_path):
    conn = db.open_db(tmp_path / "mooc.db")
    db.migrate(conn)  # second run must not fail
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    assert {"symbols", "stock_quotes", "option_contracts", "option_quotes", "events"} <= tables
    assert {
        "trade_candidates",
        "trade_signals",
        "risk_snapshots",
        "trade_journal",
        "confirmations",
    } <= tables
    assert db.schema_version(conn) == 2


def test_stock_quote_roundtrip_and_order(tmp_path):
    conn = _db(tmp_path)
    older = _stock("US.AAPL", observed=NOW - timedelta(hours=1), last=99.0)
    newer = _stock("US.AAPL", observed=NOW, last=101.0)
    repo.upsert_stock_quote(conn, older)
    repo.upsert_stock_quote(conn, newer)

    quotes = repo.stock_quotes(conn, "US.AAPL")
    assert [q.last for q in quotes] == [101.0, 99.0]
    latest = repo.latest_stock_quote(conn, "US.AAPL")
    assert latest is not None
    assert latest.last == 101.0
    assert latest.quality.source is DataSource.REALTIME
    assert latest.quality.is_stale is False


def test_stock_quote_upsert_is_idempotent(tmp_path):
    conn = _db(tmp_path)
    repo.upsert_stock_quote(conn, _stock("US.AAPL", last=100.0))
    repo.upsert_stock_quote(conn, _stock("US.AAPL", last=105.0))
    rows = repo.stock_quotes(conn, "US.AAPL")
    assert len(rows) == 1
    assert rows[0].last == 105.0


def test_historical_quote_is_not_downgraded_to_realtime(tmp_path):
    conn = _db(tmp_path)
    hist = _stock(
        "US.AAPL",
        source=DataSource.HISTORICAL,
        observed=NOW - timedelta(days=1),
        last=90.0,
    )
    repo.upsert_stock_quote(conn, hist)
    stored = repo.latest_stock_quote(conn, "US.AAPL")
    assert stored is not None
    assert stored.quality.source is DataSource.HISTORICAL
    assert stored.quality.is_stale is True


def test_option_contract_and_quote(tmp_path):
    conn = _db(tmp_path)
    contract = OptionContract(
        code="US.AAPL261218C275000",
        underlying="US.AAPL",
        expiry=date(2026, 12, 18),
        strike=275.0,
        option_type=OptionType.CALL,
        multiplier=100,
    )
    repo.upsert_option_contract(conn, contract, updated_at=NOW)
    stored = repo.option_contracts(conn, "US.AAPL")
    assert len(stored) == 1
    assert stored[0].strike == 275.0
    assert stored[0].option_type is OptionType.CALL

    snapshot = OptionSnapshot(
        code=contract.code,
        underlying="US.AAPL",
        quality=quality_for(DataSource.REALTIME, NOW, now=NOW, max_age_seconds=60),
        bid=6.4,
        ask=6.6,
        iv=0.32,
        delta=0.45,
        open_interest=1234,
        volume=56,
    )
    repo.upsert_option_quote(conn, snapshot)
    quote = repo.latest_option_quote(conn, contract.code)
    assert quote is not None
    assert (quote.bid, quote.ask) == (6.4, 6.6)
    assert quote.delta == 0.45
    assert quote.open_interest == 1234


def test_events_insert_and_filter(tmp_path):
    conn = _db(tmp_path)
    earnings = Event(
        event_type=EventType.EARNINGS,
        event_datetime=NOW + timedelta(days=3),
        observed_at=NOW,
        code="US.AAPL",
        source=DataSource.DELAYED,
    )
    macro = Event(
        event_type=EventType.ECONOMIC,
        event_datetime=NOW + timedelta(days=5),
        observed_at=NOW,
    )
    repo.insert_event(conn, earnings)
    repo.insert_event(conn, macro)
    repo.insert_event(conn, earnings)  # idempotent

    assert len(repo.events(conn)) == 2
    only_earnings = repo.events(conn, event_type=EventType.EARNINGS)
    assert [e.code for e in only_earnings] == ["US.AAPL"]
    assert only_earnings[0].event_type is EventType.EARNINGS
    assert repo.events(conn, code="US.AAPL")[0].source is DataSource.DELAYED
