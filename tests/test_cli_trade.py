from __future__ import annotations

import pytest

from mooc.cli import build_parser


@pytest.mark.parametrize("command", ["funds", "positions", "orders"])
def test_trade_probe_requires_positive_account_id(command):
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["probe", command])
    with pytest.raises(SystemExit):
        parser.parse_args(["probe", command, "--acc-id", "0"])

    args = parser.parse_args(["probe", command, "--acc-id", "42"])
    assert args.acc_id == 42
