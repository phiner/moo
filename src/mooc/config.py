"""Configuration loading for mooc.

Resolution order: defaults -> optional TOML file -> ``MOOC_*`` env overrides.
Invalid values raise ``MoocError`` so misconfiguration fails fast and clearly.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

from .opend.errors import MoocError

DEFAULT_CONFIG_PATH = Path("mooc.toml")
ENV_PREFIX = "MOOC_"
VALID_TRD_ENVS = frozenset({"SIMULATE", "REAL"})


@dataclass(frozen=True)
class OpendConfig:
    host: str = "127.0.0.1"
    port: int = 11111


@dataclass(frozen=True)
class TradingConfig:
    default_trd_env: str = "SIMULATE"
    allowed_trd_envs: tuple[str, ...] = ("SIMULATE",)
    default_currency: str = "USD"


@dataclass(frozen=True)
class UiConfig:
    market: str = "US"
    default_group: str = ""


def _default_db_path() -> Path:
    base = Path(os.environ.get("MOOC_RUNTIME_DIR", "~/.mooc")).expanduser()
    return base / "mooc.db"


@dataclass(frozen=True)
class StorageConfig:
    path: Path = field(default_factory=_default_db_path)


@dataclass(frozen=True)
class DataQualityConfig:
    """Freshness thresholds; a value older than these is flagged stale.

    Defaults are conservative starting points and fully overridable — the spec
    leaves the exact thresholds open (chapter 18).
    """

    realtime_max_age_sec: float = 60.0
    delayed_max_age_sec: float = 900.0


@dataclass(frozen=True)
class RulesConfig:
    """Directory of strategy rule files (spec ch. 14)."""

    path: Path = Path("rules")


@dataclass(frozen=True)
class AppConfig:
    opend: OpendConfig = field(default_factory=OpendConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    data_quality: DataQualityConfig = field(default_factory=DataQualityConfig)
    rules: RulesConfig = field(default_factory=RulesConfig)


def _env(name: str) -> str | None:
    return os.environ.get(ENV_PREFIX + name)


def _as_int(value: str | int, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise MoocError(f"invalid config: {field_name} must be an integer, got {value!r}") from exc


def _as_float(value: str | float, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise MoocError(f"invalid config: {field_name} must be a number, got {value!r}") from exc


def _as_trd_env(value: object, field_name: str) -> str:
    env = str(value).upper()
    if env not in VALID_TRD_ENVS:
        raise MoocError(
            f"invalid config: {field_name}={value!r} (expected one of {sorted(VALID_TRD_ENVS)})"
        )
    return env


def load_config(path: Path | None = None) -> AppConfig:
    """Load configuration from TOML (if present) then apply env overrides."""
    cfg = AppConfig()
    resolved = path or Path(_env("CONFIG") or DEFAULT_CONFIG_PATH)
    if resolved.is_file():
        with resolved.open("rb") as fh:
            cfg = _from_toml(cfg, tomllib.load(fh))
    return _apply_env(cfg)


def _from_toml(cfg: AppConfig, raw: dict) -> AppConfig:
    opend = raw.get("opend", {})
    trading = raw.get("trading", {})
    ui = raw.get("ui", {})
    storage = raw.get("storage", {})
    data_quality = raw.get("data_quality", {})
    rules = raw.get("rules", {})
    allowed = trading.get("allowed_trd_envs", cfg.trading.allowed_trd_envs)
    return AppConfig(
        opend=replace(
            cfg.opend,
            host=str(opend.get("host", cfg.opend.host)),
            port=_as_int(opend.get("port", cfg.opend.port), "opend.port"),
        ),
        trading=replace(
            cfg.trading,
            default_trd_env=_as_trd_env(
                trading.get("default_trd_env", cfg.trading.default_trd_env),
                "trading.default_trd_env",
            ),
            allowed_trd_envs=tuple(
                _as_trd_env(value, "trading.allowed_trd_envs") for value in allowed
            ),
            default_currency=str(
                trading.get("default_currency", cfg.trading.default_currency)
            ).upper(),
        ),
        ui=replace(
            cfg.ui,
            market=str(ui.get("market", cfg.ui.market)).upper(),
            default_group=str(ui.get("default_group", cfg.ui.default_group)),
        ),
        storage=replace(
            cfg.storage,
            path=Path(str(storage.get("path", cfg.storage.path))).expanduser(),
        ),
        data_quality=replace(
            cfg.data_quality,
            realtime_max_age_sec=_as_float(
                data_quality.get("realtime_max_age_sec", cfg.data_quality.realtime_max_age_sec),
                "data_quality.realtime_max_age_sec",
            ),
            delayed_max_age_sec=_as_float(
                data_quality.get("delayed_max_age_sec", cfg.data_quality.delayed_max_age_sec),
                "data_quality.delayed_max_age_sec",
            ),
        ),
        rules=replace(
            cfg.rules,
            path=Path(str(rules.get("path", cfg.rules.path))).expanduser(),
        ),
    )


def _apply_env(cfg: AppConfig) -> AppConfig:
    host = _env("OPEND_HOST")
    port = _env("OPEND_PORT")
    trd_env = _env("TRD_ENV")
    currency = _env("CURRENCY")
    default_group = _env("DEFAULT_GROUP")
    db_path = _env("DB_PATH")
    rules_path = _env("RULES_PATH")
    return AppConfig(
        opend=replace(
            cfg.opend,
            host=host or cfg.opend.host,
            port=_as_int(port, "MOOC_OPEND_PORT") if port else cfg.opend.port,
        ),
        trading=replace(
            cfg.trading,
            default_trd_env=(
                _as_trd_env(trd_env, "MOOC_TRD_ENV") if trd_env else cfg.trading.default_trd_env
            ),
            default_currency=currency.upper() if currency else cfg.trading.default_currency,
        ),
        ui=replace(
            cfg.ui,
            default_group=default_group if default_group is not None else cfg.ui.default_group,
        ),
        storage=replace(
            cfg.storage,
            path=Path(db_path).expanduser() if db_path else cfg.storage.path,
        ),
        data_quality=cfg.data_quality,
        rules=replace(
            cfg.rules,
            path=Path(rules_path).expanduser() if rules_path else cfg.rules.path,
        ),
    )
