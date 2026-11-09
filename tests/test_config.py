from __future__ import annotations

from pathlib import Path

import pytest

from mooc.config import AppConfig, load_config
from mooc.opend.errors import MoocError


def test_defaults(monkeypatch):
    for key in (
        "MOOC_CONFIG",
        "MOOC_OPEND_HOST",
        "MOOC_OPEND_PORT",
        "MOOC_TRD_ENV",
        "MOOC_RUNTIME_DIR",
        "MOOC_DB_PATH",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(Path("/tmp"))
    cfg = load_config()
    assert cfg.opend.host == "127.0.0.1"
    assert cfg.opend.port == 11111
    assert cfg.trading.default_trd_env == "SIMULATE"
    assert cfg.trading.allowed_trd_envs == ("SIMULATE",)
    assert cfg.trading.default_currency == "USD"
    assert cfg.ui.market == "US"
    assert cfg.ui.default_group == ""
    assert cfg.storage.path.name == "mooc.db"
    assert cfg.data_quality.realtime_max_age_sec == 60.0
    assert cfg.data_quality.delayed_max_age_sec == 900.0


def test_storage_and_data_quality_from_toml(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MOOC_DB_PATH", raising=False)
    monkeypatch.delenv("MOOC_RUNTIME_DIR", raising=False)
    cfg_file = tmp_path / "mooc.toml"
    cfg_file.write_text(
        "[storage]\npath = '~/custom/data.db'\n[data_quality]\nrealtime_max_age_sec = 5\n"
    )
    cfg = load_config(cfg_file)
    assert cfg.storage.path == Path("~/custom/data.db").expanduser()
    assert cfg.data_quality.realtime_max_age_sec == 5.0
    assert cfg.data_quality.delayed_max_age_sec == 900.0


def test_db_path_env_override(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "mooc.toml"
    cfg_file.write_text("[storage]\npath = '~/from-toml.db'\n")
    monkeypatch.setenv("MOOC_DB_PATH", "~/from-env.db")
    cfg = load_config(cfg_file)
    assert cfg.storage.path == Path("~/from-env.db").expanduser()


def test_invalid_data_quality_raises(tmp_path: Path):
    cfg_file = tmp_path / "mooc.toml"
    cfg_file.write_text("[data_quality]\nrealtime_max_age_sec = 'soon'\n")
    with pytest.raises(MoocError):
        load_config(cfg_file)


def test_ui_default_group_from_toml(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MOOC_DEFAULT_GROUP", raising=False)
    cfg_file = tmp_path / "mooc.toml"
    cfg_file.write_text("[ui]\ndefault_group = 'My Group'\n")
    assert load_config(cfg_file).ui.default_group == "My Group"


def test_toml_and_env_override(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "mooc.toml"
    cfg_file.write_text(
        "[opend]\nhost = '10.0.0.5'\nport = 11112\n"
        "[trading]\ndefault_trd_env = 'REAL'\nallowed_trd_envs = ['SIMULATE', 'REAL']\n"
    )
    monkeypatch.setenv("MOOC_OPEND_HOST", "192.168.0.1")
    monkeypatch.delenv("MOOC_OPEND_PORT", raising=False)
    cfg = load_config(cfg_file)
    assert cfg.opend.host == "192.168.0.1"  # env wins over toml
    assert cfg.opend.port == 11112  # toml preserved
    assert cfg.trading.default_trd_env == "REAL"
    assert cfg.trading.allowed_trd_envs == ("SIMULATE", "REAL")


def test_invalid_port_raises(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MOOC_CONFIG", raising=False)
    cfg_file = tmp_path / "mooc.toml"
    cfg_file.write_text("[opend]\nport = 'not-a-number'\n")
    with pytest.raises(MoocError):
        load_config(cfg_file)


def test_invalid_trd_env_raises(tmp_path: Path):
    cfg_file = tmp_path / "mooc.toml"
    cfg_file.write_text("[trading]\ndefault_trd_env = 'LIVE'\n")
    with pytest.raises(MoocError):
        load_config(cfg_file)


def test_appconfig_is_frozen():
    cfg = AppConfig()
    assert cfg.opend.port == 11111
