from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

pytest.importorskip("textual")

from mooc.tui.app import MoocApp


def test_workers_declare_independent_exclusive_groups():
    source = Path(inspect.getsourcefile(MoocApp))
    tree = ast.parse(source.read_text())
    methods = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    workers = {
        "_load_groups_worker": "groups",
        "_load_watchlist_worker": "watchlist",
        "_load_chain_worker": "chain",
        "_load_accounts_worker": "accounts",
        "_load_account_worker": "account",
        "_load_orders_worker": "orders",
        "_load_combo_worker": "combo",
    }

    groups = []
    for name, expected_group in workers.items():
        decorator = methods[name].decorator_list[0]
        keywords = {keyword.arg: keyword.value for keyword in decorator.keywords}
        assert ast.literal_eval(keywords["group"]) == expected_group
        assert ast.literal_eval(keywords["exclusive"]) is True
        groups.append(ast.literal_eval(keywords["group"]))

    assert len(groups) == len(set(groups))


def test_stale_success_and_error_callbacks_are_discarded():
    app = MoocApp.__new__(MoocApp)
    app._request_generations = {"chain": 2}
    calls = []

    app._post_if_current("chain", 1, calls.append, "stale success")
    app._post_if_current("chain", 2, calls.append, "current success")
    app._post_if_current("chain", 1, calls.append, "stale error")

    assert calls == ["current success"]


def test_request_generations_are_independent():
    app = MoocApp.__new__(MoocApp)
    app._request_generations = {"chain": 0, "orders": 0}

    assert app._next_generation("chain") == 1
    assert app._next_generation("orders") == 1
    assert app._next_generation("chain") == 2
    assert app._request_generations == {"chain": 2, "orders": 1}
