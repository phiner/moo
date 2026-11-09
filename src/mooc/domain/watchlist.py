"""Watchlist domain types (moomoo self-selected groups; pure data)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WatchlistGroup:
    """One self-selected security group (``get_user_security_group``)."""

    name: str
    group_type: str


@dataclass(frozen=True)
class Security:
    """One member of a watchlist group (``get_user_security``)."""

    code: str
    name: str
    stock_type: str


@dataclass(frozen=True)
class UnderlyingSummary:
    """Nearest-expiry ATM option snapshot for one watchlist underlying."""

    code: str
    name: str
    last_price: float | None
    expiry: str | None
    atm_strike: float | None
    call_bid: float | None
    call_ask: float | None
    put_bid: float | None
    put_ask: float | None
