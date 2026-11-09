"""SQLite connection setup and schema migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .schema import DDL_STATEMENTS, SCHEMA_VERSION

BUSY_TIMEOUT_MS = 5000


def connect(path: str | Path) -> sqlite3.Connection:
    """Open ``path`` (creating parent dirs), with WAL and safe defaults."""
    target = str(path)
    if target != ":memory:":
        resolved = Path(target).expanduser()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        target = str(resolved)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Create missing tables/indexes and stamp the schema version. Idempotent."""
    for statement in DDL_STATEMENTS:
        conn.execute(statement)
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    conn.commit()


def open_db(path: str | Path) -> sqlite3.Connection:
    """Connect and migrate in one step."""
    conn = connect(path)
    migrate(conn)
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row is not None else 0
