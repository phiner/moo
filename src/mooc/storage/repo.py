"""Repository: upsert and query domain objects against the SQLite schema.

Functions take an open :class:`sqlite3.Connection` and never perform network or
SDK calls. Upserts are idempotent: re-writing the same
``(code, observed_at, source)`` row updates it in place.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

from ..domain.events import Event, EventType
from ..domain.journal import Confirmation, TradeLogEntry
from ..domain.market import DataSource, OptionSnapshot, QuoteQuality, StockQuote, to_utc
from ..domain.options import OptionContract, OptionType

__all__ = [
    "add_confirmation",
    "add_journal_entry",
    "confirmations",
    "events",
    "has_decision_record",
    "insert_event",
    "journal_entries",
    "latest_option_quote",
    "latest_stock_quote",
    "option_contracts",
    "save_candidate",
    "save_risk_snapshot",
    "save_signal",
    "stock_quotes",
    "upsert_option_contract",
    "upsert_option_quote",
    "upsert_stock_quote",
    "upsert_symbol",
]


def _iso(value: datetime) -> str:
    return to_utc(value).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _missing(value: object) -> tuple[str, ...]:
    return tuple(json.loads(str(value))) if value else ()


def _quality(row: sqlite3.Row, source_index: str, observed_index: str) -> QuoteQuality:
    return QuoteQuality(
        source=DataSource(row[source_index]),
        observed_at=datetime.fromisoformat(row[observed_index]),
        is_stale=bool(row["is_stale"]),
        missing_fields=_missing(row["missing_fields"]),
    )


# -- writes ---------------------------------------------------------------
def upsert_symbol(
    conn: sqlite3.Connection,
    code: str,
    *,
    name: str = "",
    market: str = "",
    security_type: str = "",
    updated_at: datetime,
) -> None:
    conn.execute(
        """
        INSERT INTO symbols (code, name, market, security_type, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            name = excluded.name,
            market = excluded.market,
            security_type = excluded.security_type,
            updated_at = excluded.updated_at
        """,
        (code, name, market, security_type, _iso(updated_at)),
    )
    conn.commit()


def upsert_stock_quote(conn: sqlite3.Connection, quote: StockQuote) -> None:
    conn.execute(
        """
        INSERT INTO stock_quotes
            (code, observed_at, source, is_stale, last, bid, ask, volume,
             update_time, missing_fields)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code, observed_at, source) DO UPDATE SET
            is_stale = excluded.is_stale,
            last = excluded.last,
            bid = excluded.bid,
            ask = excluded.ask,
            volume = excluded.volume,
            update_time = excluded.update_time,
            missing_fields = excluded.missing_fields
        """,
        (
            quote.code,
            _iso(quote.quality.observed_at),
            quote.quality.source.value,
            int(quote.quality.is_stale),
            quote.last,
            quote.bid,
            quote.ask,
            quote.volume,
            _iso(quote.update_time) if quote.update_time else None,
            json.dumps(list(quote.quality.missing_fields)),
        ),
    )
    conn.commit()


def upsert_option_contract(
    conn: sqlite3.Connection, contract: OptionContract, *, updated_at: datetime
) -> None:
    conn.execute(
        """
        INSERT INTO option_contracts
            (code, underlying, expiry, strike, option_type, multiplier, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            underlying = excluded.underlying,
            expiry = excluded.expiry,
            strike = excluded.strike,
            option_type = excluded.option_type,
            multiplier = excluded.multiplier,
            updated_at = excluded.updated_at
        """,
        (
            contract.code,
            contract.underlying,
            contract.expiry.isoformat(),
            contract.strike,
            contract.option_type.value,
            contract.multiplier,
            _iso(updated_at),
        ),
    )
    conn.commit()


def upsert_option_quote(conn: sqlite3.Connection, snapshot: OptionSnapshot) -> None:
    conn.execute(
        """
        INSERT INTO option_quotes
            (code, underlying, observed_at, source, is_stale, last, bid, ask, iv,
             delta, gamma, theta, vega, rho, open_interest, volume, update_time,
             missing_fields)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code, observed_at, source) DO UPDATE SET
            underlying = excluded.underlying,
            is_stale = excluded.is_stale,
            last = excluded.last,
            bid = excluded.bid,
            ask = excluded.ask,
            iv = excluded.iv,
            delta = excluded.delta,
            gamma = excluded.gamma,
            theta = excluded.theta,
            vega = excluded.vega,
            rho = excluded.rho,
            open_interest = excluded.open_interest,
            volume = excluded.volume,
            update_time = excluded.update_time,
            missing_fields = excluded.missing_fields
        """,
        (
            snapshot.code,
            snapshot.underlying,
            _iso(snapshot.quality.observed_at),
            snapshot.quality.source.value,
            int(snapshot.quality.is_stale),
            snapshot.last,
            snapshot.bid,
            snapshot.ask,
            snapshot.iv,
            snapshot.delta,
            snapshot.gamma,
            snapshot.theta,
            snapshot.vega,
            snapshot.rho,
            snapshot.open_interest,
            snapshot.volume,
            _iso(snapshot.update_time) if snapshot.update_time else None,
            json.dumps(list(snapshot.quality.missing_fields)),
        ),
    )
    conn.commit()


def insert_event(conn: sqlite3.Connection, event: Event) -> None:
    conn.execute(
        """
        INSERT INTO events
            (event_type, code, event_datetime, status, source, observed_at, payload)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_type, code, event_datetime) DO UPDATE SET
            status = excluded.status,
            source = excluded.source,
            observed_at = excluded.observed_at,
            payload = excluded.payload
        """,
        (
            event.event_type.value,
            event.code,
            _iso(event.event_datetime),
            event.status,
            event.source.value,
            _iso(event.observed_at),
            event.payload,
        ),
    )
    conn.commit()


# -- reads ----------------------------------------------------------------
def _row_to_stock_quote(row: sqlite3.Row) -> StockQuote:
    return StockQuote(
        code=row["code"],
        quality=_quality(row, "source", "observed_at"),
        last=row["last"],
        bid=row["bid"],
        ask=row["ask"],
        volume=row["volume"],
        update_time=_parse_dt(row["update_time"]),
    )


def stock_quotes(conn: sqlite3.Connection, code: str, *, limit: int = 100) -> list[StockQuote]:
    rows = conn.execute(
        """
        SELECT * FROM stock_quotes WHERE code = ?
        ORDER BY observed_at DESC LIMIT ?
        """,
        (code, limit),
    ).fetchall()
    return [_row_to_stock_quote(row) for row in rows]


def latest_stock_quote(conn: sqlite3.Connection, code: str) -> StockQuote | None:
    quotes = stock_quotes(conn, code, limit=1)
    return quotes[0] if quotes else None


def option_contracts(conn: sqlite3.Connection, underlying: str) -> list[OptionContract]:
    rows = conn.execute(
        """
        SELECT * FROM option_contracts WHERE underlying = ?
        ORDER BY expiry, strike
        """,
        (underlying,),
    ).fetchall()
    return [
        OptionContract(
            code=row["code"],
            underlying=row["underlying"],
            expiry=date.fromisoformat(row["expiry"]),
            strike=row["strike"],
            option_type=OptionType(row["option_type"]),
            multiplier=row["multiplier"],
        )
        for row in rows
    ]


def _row_to_option_snapshot(row: sqlite3.Row) -> OptionSnapshot:
    return OptionSnapshot(
        code=row["code"],
        underlying=row["underlying"],
        quality=_quality(row, "source", "observed_at"),
        last=row["last"],
        bid=row["bid"],
        ask=row["ask"],
        iv=row["iv"],
        delta=row["delta"],
        gamma=row["gamma"],
        theta=row["theta"],
        vega=row["vega"],
        rho=row["rho"],
        open_interest=row["open_interest"],
        volume=row["volume"],
        update_time=_parse_dt(row["update_time"]),
    )


def latest_option_quote(conn: sqlite3.Connection, code: str) -> OptionSnapshot | None:
    row = conn.execute(
        """
        SELECT * FROM option_quotes WHERE code = ?
        ORDER BY observed_at DESC LIMIT 1
        """,
        (code,),
    ).fetchone()
    return _row_to_option_snapshot(row) if row is not None else None


def events(
    conn: sqlite3.Connection,
    *,
    event_type: EventType | None = None,
    code: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Event]:
    clauses: list[str] = []
    params: list[object] = []
    if event_type is not None:
        clauses.append("event_type = ?")
        params.append(event_type.value)
    if code is not None:
        clauses.append("code = ?")
        params.append(code)
    if start is not None:
        clauses.append("event_datetime >= ?")
        params.append(_iso(start))
    if end is not None:
        clauses.append("event_datetime <= ?")
        params.append(_iso(end))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"SELECT * FROM events {where} ORDER BY event_datetime", params).fetchall()
    return [
        Event(
            event_type=EventType(row["event_type"]),
            event_datetime=datetime.fromisoformat(row["event_datetime"]),
            observed_at=datetime.fromisoformat(row["observed_at"]),
            code=row["code"],
            status=row["status"],
            source=DataSource(row["source"]),
            payload=row["payload"],
        )
        for row in rows
    ]


# -- candidates / signals / risk snapshots --------------------------------
def save_candidate(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    strategy: str,
    status: str,
    created_at: datetime,
    payload: str = "{}",
    commit: bool = True,
) -> None:
    conn.execute(
        """
        INSERT INTO trade_candidates (symbol, strategy, status, payload, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (symbol, strategy, status, payload, _iso(created_at)),
    )
    if commit:
        conn.commit()


def save_signal(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    strategy: str,
    status: str,
    created_at: datetime,
    action: str = "",
    payload: str = "{}",
    commit: bool = True,
) -> None:
    conn.execute(
        """
        INSERT INTO trade_signals (symbol, strategy, status, action, payload, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (symbol, strategy, status, action, payload, _iso(created_at)),
    )
    if commit:
        conn.commit()


def save_risk_snapshot(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    created_at: datetime,
    payload: str = "{}",
    commit: bool = True,
) -> None:
    conn.execute(
        "INSERT INTO risk_snapshots (symbol, payload, created_at) VALUES (?, ?, ?)",
        (symbol, payload, _iso(created_at)),
    )
    if commit:
        conn.commit()


def has_decision_record(
    conn: sqlite3.Connection, *, symbol: str, strategy: str, created_at: datetime
) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM trade_candidates
        WHERE symbol = ? AND strategy = ? AND created_at = ?
        LIMIT 1
        """,
        (symbol, strategy, _iso(created_at)),
    ).fetchone()
    return row is not None


# -- journal / confirmations ----------------------------------------------
def add_journal_entry(
    conn: sqlite3.Connection, entry: TradeLogEntry, *, created_at: datetime
) -> None:
    conn.execute(
        """
        INSERT INTO trade_journal
            (symbol, strategy, status, opened_at, closed_at, entry_credit, exit_cost,
             max_loss, pnl, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.symbol,
            entry.strategy,
            entry.status,
            _iso(entry.opened_at) if entry.opened_at else None,
            _iso(entry.closed_at) if entry.closed_at else None,
            entry.entry_credit,
            entry.exit_cost,
            entry.max_loss,
            entry.pnl,
            entry.notes,
            _iso(created_at),
        ),
    )
    conn.commit()


def journal_entries(conn: sqlite3.Connection, *, symbol: str | None = None) -> list[TradeLogEntry]:
    where = "WHERE symbol = ?" if symbol is not None else ""
    params: list[object] = [symbol] if symbol is not None else []
    rows = conn.execute(
        f"SELECT * FROM trade_journal {where} ORDER BY created_at", params
    ).fetchall()
    return [
        TradeLogEntry(
            symbol=row["symbol"],
            strategy=row["strategy"],
            status=row["status"],
            opened_at=_parse_dt(row["opened_at"]),
            closed_at=_parse_dt(row["closed_at"]),
            entry_credit=row["entry_credit"],
            exit_cost=row["exit_cost"],
            max_loss=row["max_loss"],
            pnl=row["pnl"],
            notes=row["notes"],
        )
        for row in rows
    ]


def add_confirmation(conn: sqlite3.Connection, confirmation: Confirmation) -> None:
    conn.execute(
        """
        INSERT INTO confirmations (symbol, strategy, payload, confirmed_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            confirmation.symbol,
            confirmation.strategy,
            confirmation.payload,
            _iso(confirmation.confirmed_at),
        ),
    )
    conn.commit()


def confirmations(conn: sqlite3.Connection, *, symbol: str | None = None) -> list[Confirmation]:
    where = "WHERE symbol = ?" if symbol is not None else ""
    params: list[object] = [symbol] if symbol is not None else []
    rows = conn.execute(
        f"SELECT * FROM confirmations {where} ORDER BY confirmed_at", params
    ).fetchall()
    return [
        Confirmation(
            symbol=row["symbol"],
            strategy=row["strategy"],
            confirmed_at=datetime.fromisoformat(row["confirmed_at"]),
            payload=row["payload"],
        )
        for row in rows
    ]
