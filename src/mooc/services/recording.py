"""Persist analysis results (candidate / signal / risk snapshot).

Keeps the analysis path pure by taking an open connection; callers decide when
and where to record. Payloads store the full 14.1 output so a decision can be
replayed and explained later.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from ..domain.decision import DecisionOutput
from ..storage import repo

__all__ = ["record_decision"]


def record_decision(
    conn: sqlite3.Connection, output: DecisionOutput, *, created_at: datetime
) -> None:
    """Write one decision as a candidate, a signal, and a risk snapshot."""
    payload = json.dumps(output.to_dict(), ensure_ascii=False)
    strategy = str(output.strategy.get("type") or output.recommended_action)
    repo.save_candidate(
        conn,
        symbol=output.symbol,
        strategy=strategy,
        status=output.trade_status.value,
        payload=payload,
        created_at=created_at,
    )
    repo.save_signal(
        conn,
        symbol=output.symbol,
        strategy=strategy,
        status=output.trade_status.value,
        action=output.recommended_action,
        payload=payload,
        created_at=created_at,
    )
    repo.save_risk_snapshot(
        conn,
        symbol=output.symbol,
        payload=json.dumps(output.risk, ensure_ascii=False),
        created_at=created_at,
    )
