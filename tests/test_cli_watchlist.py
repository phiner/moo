from __future__ import annotations

import pytest

from mooc.cli import build_parser


def test_probe_groups_parses():
    args = build_parser().parse_args(["probe", "groups"])
    assert args.json is False


def test_probe_watchlist_parses():
    args = build_parser().parse_args(["probe", "watchlist", "Mine", "--limit", "5"])
    assert args.group == "Mine"
    assert args.limit == 5


def test_probe_watchlist_limit_must_be_positive():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["probe", "watchlist", "Mine", "--limit", "0"])
