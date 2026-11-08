"""Shared helpers for decoding ``moomoo-api`` responses (option + trade)."""

from __future__ import annotations

from .errors import OpendRejected

_MISSING = {"", "N/A", "NAN", "--"}


def require_ok(api: str, ret, data) -> None:
    """Raise ``OpendRejected`` unless the SDK call returned ``RET_OK``."""
    from moomoo import RET_OK

    if ret != RET_OK:
        raise OpendRejected(api, str(data))


def to_float(value) -> float | None:
    """Parse a numeric cell, mapping SDK missing markers to ``None``."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in _MISSING:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value) -> int | None:
    number = to_float(value)
    return int(number) if number is not None else None
