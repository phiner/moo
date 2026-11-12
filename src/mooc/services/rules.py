"""Load and validate strategy rules from YAML (spec ch. 14).

YAML is used because the spec represents undetermined parameters as ``null``,
which TOML cannot express. Loading is strict: malformed files raise ``MoocError``
so misconfiguration fails fast.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import yaml

from ..domain.rules import UNSET, Maybe, Regimes, StrategyRule, Unset
from ..opend.errors import MoocError

__all__ = ["compute_rules_version", "load_rules", "parse_rule"]

_DEFAULT_SUFFIXES = (".yaml", ".yml")


def _maybe(section: dict, key: str) -> Maybe:
    if key not in section:
        return UNSET
    value = section[key]
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise MoocError(f"rule field {key!r} must be a number or null, got {value!r}") from exc


def _regimes(section: dict, key: str) -> Regimes:
    if key not in section:
        return UNSET
    value = section[key]
    if value is None:
        return None
    if not isinstance(value, list):
        raise MoocError(f"rule field {key!r} must be a list of regime names or null")
    return tuple(str(item) for item in value)


def parse_rule(document: dict) -> StrategyRule:
    """Parse one YAML document (or the ``{strategy: ...}`` wrapper)."""
    if not isinstance(document, dict):
        raise MoocError("rule document must be a mapping")
    body = document.get("strategy", document)
    if not isinstance(body, dict):
        raise MoocError("rule 'strategy' must be a mapping")
    name = body.get("name")
    if not name:
        raise MoocError("rule is missing a 'name'")

    market = body.get("market_conditions") or {}
    volatility = body.get("volatility") or {}
    expiration = body.get("expiration") or {}
    short_leg = body.get("short_leg") or {}
    spread = body.get("spread") or {}
    exit_ = body.get("exit") or {}
    risk = body.get("risk") or {}
    for section, key in (
        (market, "market_conditions"),
        (volatility, "volatility"),
        (expiration, "expiration"),
        (short_leg, "short_leg"),
        (spread, "spread"),
        (exit_, "exit"),
        (risk, "risk"),
    ):
        if not isinstance(section, dict):
            raise MoocError(f"rule section {key!r} must be a mapping")

    return StrategyRule(
        name=str(name),
        enabled=bool(body.get("enabled", True)),
        allowed_regimes=_regimes(market, "allowed_regimes"),
        iv_rank_min=_maybe(volatility, "iv_rank_min"),
        iv_rank_max=_maybe(volatility, "iv_rank_max"),
        iv_percentile_min=_maybe(volatility, "iv_percentile_min"),
        min_dte=_maybe(expiration, "min_dte"),
        max_dte=_maybe(expiration, "max_dte"),
        delta_min=_maybe(short_leg, "delta_min"),
        delta_max=_maybe(short_leg, "delta_max"),
        min_width=_maybe(spread, "min_width"),
        max_width=_maybe(spread, "max_width"),
        take_profit_pct=_maybe(exit_, "take_profit_pct"),
        stop_review_multiple=_maybe(exit_, "stop_review_multiple"),
        time_exit_dte=_maybe(exit_, "time_exit_dte"),
        max_account_risk_pct=_maybe(risk, "max_account_risk_pct"),
    )


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_dir():
        for candidate in sorted(path.iterdir()):
            if candidate.suffix.lower() in _DEFAULT_SUFFIXES:
                yield candidate
    elif path.is_file():
        yield path
    else:
        raise MoocError(f"rules path not found: {path}")


def load_rules(path: str | Path) -> list[StrategyRule]:
    """Load every ``*.yaml`` under ``path`` (a file or a directory)."""
    rules: list[StrategyRule] = []
    for file in _iter_files(Path(path)):
        try:
            document = yaml.safe_load(file.read_text())
        except yaml.YAMLError as exc:
            raise MoocError(f"invalid YAML in {file}: {exc}") from exc
        if document is None:
            continue
        rules.append(parse_rule(document))
    return rules


def _normalize_rule_value(value: Any) -> Any:
    if isinstance(value, Unset):
        return {"__unset__": True}
    if isinstance(value, tuple):
        return [_normalize_rule_value(v) for v in value]
    if isinstance(value, list):
        return [_normalize_rule_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _normalize_rule_value(v) for k, v in sorted(value.items())}
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize_rule_value(asdict(value))
    return value


def compute_rules_version(rules: list[StrategyRule], rules_path: str | Path | None = None) -> str:
    """Deterministic SHA-256 fingerprint of the effective loaded rules."""
    payload = {
        "rules_path": str(rules_path) if rules_path is not None else None,
        "rules": [_normalize_rule_value(rule) for rule in rules],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
