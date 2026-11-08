"""Error types for the OpenD/SDK access layer."""

from __future__ import annotations


class MoocError(Exception):
    """Base class for all mooc errors."""


class OpendUnavailable(MoocError):
    """OpenD is not reachable (not running, wrong host/port)."""


class OpendRejected(MoocError):
    """OpenD or the SDK rejected a request."""

    def __init__(self, api: str, message: str) -> None:
        super().__init__(f"{api}: {message}")
        self.api = api
        self.message = message


class TradingDisabled(MoocError):
    """A trading request was blocked by the local safety policy."""
