from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Label

from mooc.tui import app as app_module
from mooc.tui.app import MoocApp


def test_on_mount_keys_watchlist_columns_by_label():
    tree = ast.parse(Path(inspect.getsourcefile(MoocApp)).read_text())
    on_mount = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "on_mount"
    )
    add_column_calls = [
        node
        for node in ast.walk(on_mount)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_column"
    ]
    assert add_column_calls, "watchlist columns must be added with add_column"
    assert all(any(kw.arg == "key" for kw in call.keywords) for call in add_column_calls)


class _Harness(App):
    """Minimal app exposing just the watchlist widgets and the two helpers."""

    _add_member_rows = MoocApp._add_member_rows
    _fill_row = MoocApp._fill_row

    def compose(self) -> ComposeResult:
        yield Label("", id="watchlist-title")
        yield DataTable(id="watchlist")

    def on_mount(self) -> None:
        table = self.query_one("#watchlist", DataTable)
        for label in ("code", *app_module._SUMMARY_COLUMNS):
            table.add_column(label, key=label)


def test_members_show_immediately_then_fill():
    async def scenario() -> None:
        async with _Harness().run_test() as pilot:
            app = pilot.app
            table = app.query_one("#watchlist", DataTable)
            app._add_member_rows([("US.A", "Apple"), ("US.B", "Beta")])
            assert table.get_row("US.A")[0:2] == ["US.A", "Apple"]
            assert table.get_row("US.B")[0:2] == ["US.B", "Beta"]
            assert table.get_row("US.A")[2] == "-"  # option columns not filled yet

            app._fill_row("G", ("US.A", "Apple", "1.00", "2099-01-15", "10.00", "1/2", "3/4"), 1, 2)
            row = table.get_row("US.A")
            assert row[2:] == ["1.00", "2099-01-15", "10.00", "1/2", "3/4"]

    asyncio.run(asyncio.wait_for(scenario(), timeout=20))


def test_fill_row_of_absent_code_is_ignored():
    async def scenario() -> None:
        async with _Harness().run_test() as pilot:
            pilot.app._fill_row("G", ("US.NOPE", "Nope", "1", "-", "-", "-", "-"), 1, 1)

    asyncio.run(asyncio.wait_for(scenario(), timeout=20))
