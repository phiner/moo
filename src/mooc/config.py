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


@dataclass(frozen=True)
class AppConfig:
    opend: OpendConfig = field(default_factory=OpendConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    ui: UiConfig = field(default_factory=UiConfig)


def _env(name: str) -> str | None:
    return os.environ.get(ENV_PREFIX + name)


def _as_int(value: str | int, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise MoocError(f"invalid config: {field_name} must be an integer, got {value!r}") from exc


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
        ui=replace(cfg.ui, market=str(ui.get("market", cfg.ui.market)).upper()),
    )


def _apply_env(cfg: AppConfig) -> AppConfig:
    host = _env("OPEND_HOST")
    port = _env("OPEND_PORT")
    trd_env = _env("TRD_ENV")
    currency = _env("CURRENCY")
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
        ui=cfg.ui,
    )
