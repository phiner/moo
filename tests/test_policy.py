from __future__ import annotations

from dataclasses import replace

import pytest

from mooc.config import AppConfig
from mooc.opend.errors import TradingDisabled
from mooc.policy import resolve_trd_env


def test_default_env_is_simulate():
    assert resolve_trd_env(None, AppConfig().trading) == "SIMULATE"


def test_requested_env_is_normalized():
    assert resolve_trd_env("simulate", AppConfig().trading) == "SIMULATE"


def test_allowed_env_passes():
    trading = replace(
        AppConfig().trading, default_trd_env="REAL", allowed_trd_envs=("SIMULATE", "REAL")
    )
    assert resolve_trd_env("REAL", trading) == "REAL"


def test_disallowed_env_raises():
    with pytest.raises(TradingDisabled):
        resolve_trd_env("REAL", AppConfig().trading)
