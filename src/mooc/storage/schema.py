"""SQLite DDL for the data layer (spec chapter 13.3).

Every market-bearing table carries ``observed_at``, ``source``, and ``is_stale``
so realtime history can never be confused with delayed/historical data. Tables
for later phases (signals, candidates, risk snapshots, journal) are added via
new migrations as those phases land.
"""

from __future__ import annotations

SCHEMA_VERSION = 1

DDL_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS symbols (
        code          TEXT PRIMARY KEY,
        name          TEXT NOT NULL DEFAULT '',
        market        TEXT NOT NULL DEFAULT '',
        security_type TEXT NOT NULL DEFAULT '',
        updated_at    TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stock_quotes (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        code           TEXT NOT NULL,
        observed_at    TEXT NOT NULL,
        source         TEXT NOT NULL,
        is_stale       INTEGER NOT NULL DEFAULT 0,
        last           REAL,
        bid            REAL,
        ask            REAL,
        volume         INTEGER,
        update_time    TEXT,
        missing_fields TEXT NOT NULL DEFAULT '[]',
        UNIQUE (code, observed_at, source)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_stock_quotes_code_time
        ON stock_quotes (code, observed_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS option_contracts (
        code        TEXT PRIMARY KEY,
        underlying  TEXT NOT NULL,
        expiry      TEXT NOT NULL,
        strike      REAL NOT NULL,
        option_type TEXT NOT NULL,
        multiplier  INTEGER NOT NULL DEFAULT 100,
        updated_at  TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_option_contracts_underlying
        ON option_contracts (underlying, expiry)
    """,
    """
    CREATE TABLE IF NOT EXISTS option_quotes (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        code           TEXT NOT NULL,
        underlying     TEXT NOT NULL,
        observed_at    TEXT NOT NULL,
        source         TEXT NOT NULL,
        is_stale       INTEGER NOT NULL DEFAULT 0,
        last           REAL,
        bid            REAL,
        ask            REAL,
        iv             REAL,
        delta          REAL,
        gamma          REAL,
        theta          REAL,
        vega           REAL,
        rho            REAL,
        open_interest  INTEGER,
        volume         INTEGER,
        update_time    TEXT,
        missing_fields TEXT NOT NULL DEFAULT '[]',
        UNIQUE (code, observed_at, source)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_option_quotes_code_time
        ON option_quotes (code, observed_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type     TEXT NOT NULL,
        code           TEXT,
        event_datetime TEXT NOT NULL,
        status         TEXT NOT NULL DEFAULT 'upcoming',
        source         TEXT NOT NULL,
        observed_at    TEXT NOT NULL,
        payload        TEXT NOT NULL DEFAULT '{}',
        UNIQUE (event_type, code, event_datetime)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_events_time
        ON events (event_datetime)
    """,
)
