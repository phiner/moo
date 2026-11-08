"""Textual client: option chain browse + strategy (combo) builder.

IPC calls are blocking, so they run in Textual workers (threads) and results are
marshalled back to the UI thread. Expirations default to the first non-past date.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    TabbedContent,
    TabPane,
)

from ..ipc import protocol
from ..ipc.client import IpcClient
from ..opend.errors import MoocError


class MoocApp(App):
    """S1 projection: option chain and combo bid/ask analysis."""

    BINDINGS: ClassVar = [("q", "quit", "Quit"), ("r", "reload", "Reload")]
    CSS = """
    #chain { height: 1fr; }
    #chain-title { padding: 0 1; }
    #combo-result { padding: 1; }
    """

    def __init__(self, socket_path: Path) -> None:
        super().__init__()
        self._ipc = IpcClient(socket_path)
        self._underlying = "US.AAPL"

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Chain", id="tab-chain"):
                yield Input(
                    value=self._underlying,
                    placeholder="underlying, e.g. US.AAPL",
                    id="underlying",
                )
                yield Label("loading…", id="chain-title")
                yield DataTable(id="chain")
            with TabPane("Strategy", id="tab-strategy"):
                yield Input(
                    placeholder='legs JSON, e.g. [{"code":"US.AAPL261118C270000","action":"BUY","quantity":1}]',
                    id="legs",
                )
                yield Static(
                    "Enter legs JSON and press Enter to get combo bid/ask + P&L.",
                    id="combo-result",
                )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#chain", DataTable).add_columns("code", "expiry", "type", "strike")
        self._load_chain()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "underlying":
            self._underlying = event.value.strip() or self._underlying
            self._load_chain()
        elif event.input.id == "legs":
            self._load_combo(event.value.strip())

    def action_reload(self) -> None:
        self._load_chain()

    # -- chain -------------------------------------------------------------
    @work(exclusive=True, thread=True)
    def _load_chain(self) -> None:
        underlying = self._underlying
        try:
            expirations = self._ipc.request(protocol.GetOptionExpirations(underlying=underlying))
            if expirations.kind != "OptionExpirationsResult":
                raise MoocError(getattr(expirations, "message", "unexpected response"))
            today = date.today().isoformat()
            expiry = next((value for value in expirations.dates if value >= today), None)
            if expiry is None:
                self.call_from_thread(
                    self._show_chain_error, f"{underlying}: no active expirations"
                )
                return
            chain = self._ipc.request(
                protocol.GetOptionChain(underlying=underlying, start=expiry, end=expiry)
            )
            if chain.kind != "OptionChainResult":
                raise MoocError(getattr(chain, "message", "unexpected chain response"))
            rows = [
                (c.code, c.expiry, c.option_type, f"{c.strike:.2f}") for c in chain.contracts[:200]
            ]
            self.call_from_thread(self._show_chain, underlying, expiry, rows, len(chain.contracts))
        except Exception as exc:  # noqa: BLE001 - report any failure in the UI
            self.call_from_thread(self._show_chain_error, f"error: {exc}")

    def _show_chain(self, underlying: str, expiry: str, rows, total: int) -> None:
        table = self.query_one("#chain", DataTable)
        table.clear()
        for row in rows:
            table.add_row(*row)
        self.query_one("#chain-title", Label).update(f"{underlying} @ {expiry} — {total} contracts")

    def _show_chain_error(self, message: str) -> None:
        self.query_one("#chain", DataTable).clear()
        self.query_one("#chain-title", Label).update(message)

    # -- strategy ----------------------------------------------------------
    @work(exclusive=True, thread=True)
    def _load_combo(self, raw: str) -> None:
        if not raw:
            self.call_from_thread(self._show_combo, "Enter legs JSON first.")
            return
        try:
            legs = [protocol.Leg.model_validate(item) for item in json.loads(raw)]
            response = self._ipc.request(protocol.GetComboAnalysis(legs=legs))
            if response.kind != "ComboAnalysisResult":
                raise MoocError(getattr(response, "message", "unexpected response"))
            text = "\n".join(
                [
                    f"{response.name} ({response.strategy}) [{response.code}]",
                    f"combo bid/ask  : {response.bid1:.2f} / {response.ask1:.2f}",
                    f"max profit/loss: {response.max_profit:.2f} / {response.max_loss:.2f}",
                    f"breakeven      : {[round(x, 2) for x in response.breakeven]}",
                    f"prob of profit : {response.prob_profit:.2f}",
                    f"delta/theta    : {response.delta:.4f} / {response.theta:.4f}",
                ]
            )
        except Exception as exc:  # noqa: BLE001 - report any failure in the UI
            text = f"error: {exc}"
        self.call_from_thread(self._show_combo, text)

    def _show_combo(self, text: str) -> None:
        self.query_one("#combo-result", Static).update(text)


def run(socket_path: Path) -> None:
    MoocApp(socket_path).run()
