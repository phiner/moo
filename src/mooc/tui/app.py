"""Textual client.

Default view is the Watchlist tab: the self-selected groups' underlyings with a
nearest-expiry ATM option summary. Selecting a row opens its full chain in the
Chain tab, which also keeps a manual symbol input.

IPC calls are blocking, so they run in Textual workers (threads) and results are
marshalled back to the UI thread. Stale responses are dropped by a per-view
request generation.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
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
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from ..ipc import protocol
from ..ipc.client import IpcClient
from ..opend.errors import MoocError

# Members load in one call and are shown at once; only option data is throttled
# (OpenD allows 10 chains per rolling 30 seconds), so pause every 10 fills.
WATCHLIST_BATCH = 10
WATCHLIST_WINDOW_SECONDS = 31.0
WATCHLIST_REQUEST_TIMEOUT = 45.0

# Watchlist columns that a summary fills in, in order (code is the row key).
_SUMMARY_COLUMNS = ("name", "last", "expiry", "atm", "call", "put")


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:,.2f}"


def _pair(bid: float | None, ask: float | None) -> str:
    if bid is None and ask is None:
        return "-"
    return f"{_fmt(bid)}/{_fmt(ask)}"


def _summary_row(item) -> tuple:
    return (
        item.code,
        item.name,
        _fmt(item.last_price),
        item.expiry or "-",
        _fmt(item.atm_strike),
        _pair(item.call_bid, item.call_ask),
        _pair(item.put_bid, item.put_ask),
    )


class MoocApp(App):
    """Projection over the daemon: option chain, combo analysis, account, orders."""

    BINDINGS: ClassVar = [("q", "quit", "Quit"), ("r", "reload", "Reload")]
    CSS = """
    #watchlist { height: 1fr; }
    #watchlist-title { padding: 0 1; }
    #chain { height: 1fr; }
    #chain-title { padding: 0 1; }
    #combo-result { padding: 1; }
    #account-title { padding: 0 1; }
    #positions { height: 1fr; }
    #orders-title { padding: 0 1; }
    #orders { height: 1fr; }
    """

    def __init__(self, socket_path: Path, default_group: str = "") -> None:
        super().__init__()
        self._ipc = IpcClient(socket_path)
        self._underlying = "US.AAPL"
        self._default_group = default_group
        self._group: str | None = None
        self._account_id: int | None = None
        self._request_generations = {
            "groups": 0,
            "watchlist": 0,
            "chain": 0,
            "accounts": 0,
            "account": 0,
            "orders": 0,
            "combo": 0,
            "analysis": 0,
            "journal": 0,
        }
        self._analysis_symbol = "US.AAPL"

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Watchlist", id="tab-watchlist"):
                yield Select([], prompt="Choose group", allow_blank=True, id="group-select")
                yield Label("loading…", id="watchlist-title")
                yield DataTable(id="watchlist")
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
            with TabPane("Account", id="tab-account"):
                yield Select([], prompt="Choose account", allow_blank=True, id="account-select")
                yield Label("loading…", id="account-title")
                yield DataTable(id="positions")
            with TabPane("Orders", id="tab-orders"):
                yield Label("loading…", id="orders-title")
                yield DataTable(id="orders")
            with TabPane("Analysis", id="tab-analysis"):
                yield Input(
                    value=self._analysis_symbol,
                    placeholder="symbol, e.g. US.AAPL",
                    id="analysis-symbol",
                )
                yield Static(
                    "Enter a symbol and press Enter for the analysis.", id="analysis-result"
                )
            with TabPane("Journal", id="tab-journal"):
                yield Static("loading…", id="journal-result")
        yield Footer()

    def on_mount(self) -> None:
        watchlist_table = self.query_one("#watchlist", DataTable)
        for label in ("code", *_SUMMARY_COLUMNS):
            watchlist_table.add_column(label, key=label)
        self.query_one("#chain", DataTable).add_columns("code", "expiry", "type", "strike")
        self.query_one("#positions", DataTable).add_columns(
            "code", "qty", "avg_cost", "market_val", "pl_val", "side"
        )
        self.query_one("#orders", DataTable).add_columns(
            "order_id", "code", "side", "status", "qty", "price"
        )
        self._load_groups()
        self._load_accounts()
        self._load_journal()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "underlying":
            self._underlying = event.value.strip() or self._underlying
            self._load_chain()
        elif event.input.id == "legs":
            self._load_combo(event.value.strip())
        elif event.input.id == "analysis-symbol":
            self._analysis_symbol = event.value.strip() or self._analysis_symbol
            self._load_analysis()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "account-select":
            account_id = event.value if isinstance(event.value, int) else None
            if account_id != self._account_id:
                self._account_id = account_id
                self._load_account()
                self._load_orders()
        elif event.select.id == "group-select":
            group = event.value if isinstance(event.value, str) and event.value else None
            if group != self._group:
                self._group = group
                self._load_watchlist()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id != "watchlist":
            return
        code = event.row_key.value if event.row_key.value else None
        if not code:
            return
        self._underlying = code
        input_widget = self.query_one("#underlying", Input)
        input_widget.value = code
        self.query_one(TabbedContent).active = "tab-chain"
        self._load_chain()

    def action_reload(self) -> None:
        self._load_groups()
        self._load_accounts()
        self._load_journal()

    def _next_generation(self, group: str) -> int:
        self._request_generations[group] += 1
        return self._request_generations[group]

    def _post_if_current(self, group: str, generation: int, callback: Callable, *args) -> None:
        if generation == self._request_generations[group]:
            callback(*args)

    def _show_if_current(self, group: str, generation: int, callback: Callable, *args) -> None:
        self.call_from_thread(self._post_if_current, group, generation, callback, *args)

    # -- watchlist ---------------------------------------------------------
    def _load_groups(self) -> None:
        generation = self._next_generation("groups")
        self._load_groups_worker(generation)

    @work(group="groups", exclusive=True, thread=True)
    def _load_groups_worker(self, generation: int) -> None:
        try:
            response = self._ipc.request(protocol.GetWatchlistGroups())
            if response.kind != "WatchlistGroupsResult":
                raise MoocError(getattr(response, "message", "unexpected response"))
            options = [(group.name, group.name) for group in response.groups]
            custom = [group.name for group in response.groups if group.group_type == "CUSTOM"]
            self._show_if_current("groups", generation, self._show_groups, options, custom)
        except Exception as exc:  # noqa: BLE001 - report any failure in the UI
            self._show_if_current("groups", generation, self._show_watchlist_error, f"error: {exc}")

    def _show_groups(self, options, custom) -> None:
        selector = self.query_one("#group-select", Select)
        selector.set_options(options)
        names = [name for name, _ in options]
        if self._default_group and self._default_group in names:
            chosen = self._default_group
        elif custom:
            chosen = custom[0]
        elif names:
            chosen = names[0]
        else:
            chosen = None
        if chosen is None:
            self._group = None
            self._show_watchlist_error("no self-selected groups found")
            return
        selector.value = chosen

    def _load_watchlist(self) -> None:
        generation = self._next_generation("watchlist")
        group = self._group
        if group is None:
            self._show_watchlist_error("choose a group")
            return
        self._load_watchlist_worker(group, generation)

    @work(group="watchlist", exclusive=True, thread=True)
    def _load_watchlist_worker(self, group: str, generation: int) -> None:
        try:
            response = self._ipc.request(protocol.GetWatchlistMembers(group_name=group))
            if response.kind != "WatchlistMembersResult":
                raise MoocError(getattr(response, "message", "unexpected response"))
            members = response.items
            total = len(members)
            if total == 0:
                self._show_if_current(
                    "watchlist", generation, self._show_watchlist_error, f"{group}: no underlyings"
                )
                return
            self._show_if_current("watchlist", generation, self._begin_watchlist, group, total)
            self._show_if_current(
                "watchlist",
                generation,
                self._add_member_rows,
                [(member.code, member.name) for member in members],
            )
            for index, member in enumerate(members):
                if index and index % WATCHLIST_BATCH == 0:
                    self._show_if_current(
                        "watchlist",
                        generation,
                        self._waiting_watchlist,
                        group,
                        index,
                        total,
                    )
                    time.sleep(WATCHLIST_WINDOW_SECONDS)
                try:
                    summary = self._ipc.request(
                        protocol.GetUnderlyingSummary(code=member.code, name=member.name),
                        timeout=WATCHLIST_REQUEST_TIMEOUT,
                    )
                    if summary.kind != "UnderlyingSummaryResult" or summary.item is None:
                        raise MoocError(getattr(summary, "message", "unexpected response"))
                    row = _summary_row(summary.item)
                except Exception as exc:  # noqa: BLE001 - one bad symbol must not stop the rest
                    row = (member.code, member.name, "-", "-", "-", "-", f"error: {exc}")
                self._show_if_current(
                    "watchlist", generation, self._fill_row, group, row, index + 1, total
                )
        except Exception as exc:  # noqa: BLE001 - report any failure in the UI
            self._show_if_current(
                "watchlist", generation, self._show_watchlist_error, f"error: {exc}"
            )

    def _begin_watchlist(self, group: str, total: int) -> None:
        self.query_one("#watchlist", DataTable).clear()
        self.query_one("#watchlist-title", Label).update(f"{group} — 0/{total} loaded")

    def _add_member_rows(self, members) -> None:
        table = self.query_one("#watchlist", DataTable)
        existing = {key.value for key in table.rows}
        for code, name in members:
            if code in existing:
                continue
            table.add_row(code, name, "-", "-", "-", "-", "-", key=code)

    def _fill_row(self, group: str, row, filled: int, total: int) -> None:
        table = self.query_one("#watchlist", DataTable)
        code = row[0]
        if code not in {key.value for key in table.rows}:
            return
        for column, value in zip(_SUMMARY_COLUMNS, row[1:]):
            table.update_cell(code, column, value)
        suffix = f"{total} underlyings" if filled >= total else f"{filled}/{total} loaded"
        self.query_one("#watchlist-title", Label).update(f"{group} — {suffix}")

    def _waiting_watchlist(self, group: str, filled: int, total: int) -> None:
        self.query_one("#watchlist-title", Label).update(
            f"{group} — waiting for rate window ({filled}/{total} loaded)"
        )

    def _show_watchlist_error(self, message: str) -> None:
        self.query_one("#watchlist", DataTable).clear()
        self.query_one("#watchlist-title", Label).update(message)

    # -- chain -------------------------------------------------------------
    def _load_chain(self) -> None:
        generation = self._next_generation("chain")
        self._load_chain_worker(self._underlying, generation)

    @work(group="chain", exclusive=True, thread=True)
    def _load_chain_worker(self, underlying: str, generation: int) -> None:
        try:
            expirations = self._ipc.request(protocol.GetOptionExpirations(underlying=underlying))
            if expirations.kind != "OptionExpirationsResult":
                raise MoocError(getattr(expirations, "message", "unexpected response"))
            today = date.today().isoformat()
            expiry = next((value for value in expirations.dates if value >= today), None)
            if expiry is None:
                self._show_if_current(
                    "chain",
                    generation,
                    self._show_chain_error,
                    f"{underlying}: no active expirations",
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
            self._show_if_current(
                "chain",
                generation,
                self._show_chain,
                underlying,
                expiry,
                rows,
                len(chain.contracts),
            )
        except Exception as exc:  # noqa: BLE001 - report any failure in the UI
            self._show_if_current("chain", generation, self._show_chain_error, f"error: {exc}")

    def _show_chain(self, underlying: str, expiry: str, rows, total: int) -> None:
        table = self.query_one("#chain", DataTable)
        table.clear()
        for row in rows:
            table.add_row(*row)
        self.query_one("#chain-title", Label).update(f"{underlying} @ {expiry} — {total} contracts")

    def _show_chain_error(self, message: str) -> None:
        self.query_one("#chain", DataTable).clear()
        self.query_one("#chain-title", Label).update(message)

    # -- account -----------------------------------------------------------
    def _load_accounts(self) -> None:
        generation = self._next_generation("accounts")
        self._load_accounts_worker(generation)

    @work(group="accounts", exclusive=True, thread=True)
    def _load_accounts_worker(self, generation: int) -> None:
        try:
            response = self._ipc.request(protocol.GetAccounts())
            if response.kind != "AccountsResult":
                raise MoocError(getattr(response, "message", "unexpected response"))
            accounts = response.accounts
            options = [
                (f"{account.acc_id} · {account.trd_env} · {account.acc_type}", account.acc_id)
                for account in accounts
            ]
            self._show_if_current("accounts", generation, self._show_accounts, options)
        except Exception as exc:  # noqa: BLE001 - report any failure in the UI
            self._show_if_current(
                "accounts", generation, self._show_accounts_error, f"error: {exc}"
            )

    def _show_accounts(self, options) -> None:
        selector = self.query_one("#account-select", Select)
        previous = self._account_id
        selector.set_options(options)
        if previous is not None and any(value == previous for _, value in options):
            selector.value = previous
            self._load_account()
            self._load_orders()
        else:
            self._account_id = None
            self._load_account()
            self._load_orders()

    def _show_accounts_error(self, message: str) -> None:
        selector = self.query_one("#account-select", Select)
        selector.set_options([])
        self._account_id = None
        self._load_account()
        self._load_orders()
        self.query_one("#account-title", Label).update(message)
        self.query_one("#orders-title", Label).update(message)

    def _load_account(self) -> None:
        generation = self._next_generation("account")
        account_id = self._account_id
        if account_id is None:
            self._show_account("choose an account", [])
            return
        self._load_account_worker(account_id, generation)

    @work(group="account", exclusive=True, thread=True)
    def _load_account_worker(self, account_id: int, generation: int) -> None:
        try:
            funds = self._ipc.request(protocol.GetFunds(acc_id=account_id))
            if funds.kind != "FundsResult":
                raise MoocError(getattr(funds, "message", "unexpected response"))
            positions = self._ipc.request(protocol.GetPositions(acc_id=account_id))
            if positions.kind != "PositionsResult":
                raise MoocError(getattr(positions, "message", "unexpected response"))
            if funds.funds is None:
                summary = "no funds"
            else:
                f = funds.funds
                summary = (
                    f"{f.trd_env} {f.currency}  total={_fmt(f.total_assets)} "
                    f"cash={_fmt(f.cash)} avail={_fmt(f.available_funds)} "
                    f"mv={_fmt(f.market_val)} upl={_fmt(f.unrealized_pl)}"
                )
            rows = [
                (
                    p.code,
                    f"{p.qty:g}",
                    _fmt(p.average_cost),
                    _fmt(p.market_val),
                    _fmt(p.pl_val),
                    p.position_side,
                )
                for p in positions.positions
            ]
            self._show_if_current(
                "account", generation, self._show_account, f"account {account_id}: {summary}", rows
            )
        except Exception as exc:  # noqa: BLE001 - report any failure in the UI
            self._show_if_current("account", generation, self._show_account_error, f"error: {exc}")

    def _show_account(self, summary: str, rows) -> None:
        table = self.query_one("#positions", DataTable)
        table.clear()
        for row in rows:
            table.add_row(*row)
        self.query_one("#account-title", Label).update(f"{summary} — {len(rows)} positions")

    def _show_account_error(self, message: str) -> None:
        self.query_one("#positions", DataTable).clear()
        self.query_one("#account-title", Label).update(message)

    # -- orders ------------------------------------------------------------
    def _load_orders(self) -> None:
        generation = self._next_generation("orders")
        account_id = self._account_id
        if account_id is None:
            self._show_orders(None, [])
            return
        self._load_orders_worker(account_id, generation)

    @work(group="orders", exclusive=True, thread=True)
    def _load_orders_worker(self, account_id: int, generation: int) -> None:
        try:
            orders = self._ipc.request(protocol.GetOrders(acc_id=account_id))
            if orders.kind != "OrdersResult":
                raise MoocError(getattr(orders, "message", "unexpected response"))
            rows = [
                (o.order_id, o.code, o.trd_side, o.order_status, f"{o.qty:g}", f"{o.price:.2f}")
                for o in orders.orders
            ]
            self._show_if_current("orders", generation, self._show_orders, account_id, rows)
        except Exception as exc:  # noqa: BLE001 - report any failure in the UI
            self._show_if_current("orders", generation, self._show_orders_error, f"error: {exc}")

    def _show_orders(self, account_id: int | None, rows) -> None:
        table = self.query_one("#orders", DataTable)
        table.clear()
        for row in rows:
            table.add_row(*row)
        title = "choose an account" if account_id is None else f"account {account_id} — open orders"
        self.query_one("#orders-title", Label).update(f"{title} — {len(rows)}")

    def _show_orders_error(self, message: str) -> None:
        self.query_one("#orders", DataTable).clear()
        self.query_one("#orders-title", Label).update(message)

    # -- strategy ----------------------------------------------------------
    def _load_combo(self, raw: str) -> None:
        generation = self._next_generation("combo")
        self._load_combo_worker(raw, generation)

    @work(group="combo", exclusive=True, thread=True)
    def _load_combo_worker(self, raw: str, generation: int) -> None:
        if not raw:
            self._show_if_current("combo", generation, self._show_combo, "Enter legs JSON first.")
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
        self._show_if_current("combo", generation, self._show_combo, text)

    def _show_combo(self, text: str) -> None:
        self.query_one("#combo-result", Static).update(text)

    # -- analysis ----------------------------------------------------------
    def _load_analysis(self) -> None:
        generation = self._next_generation("analysis")
        self._load_analysis_worker(self._analysis_symbol, generation)

    @work(group="analysis", exclusive=True, thread=True)
    def _load_analysis_worker(self, symbol: str, generation: int) -> None:
        try:
            response = self._ipc.request(protocol.GetAnalysis(code=symbol), timeout=120.0)
            if response.kind != "AnalysisResult":
                raise MoocError(getattr(response, "message", "unexpected response"))
            output = response.output
            strategy = output.get("strategy") or {}
            risk = output.get("risk") or {}
            lines = [
                f"{output.get('symbol')} @ {output.get('analysis_timestamp')}",
                f"  data_quality     : {output.get('data_quality')}",
                f"  market_regime    : {output.get('market_regime')}",
                f"  volatility_regime: {output.get('volatility_regime')}",
                f"  event_risk       : {output.get('event_risk')}",
                f"  action           : {output.get('recommended_action')}",
                f"  trade_status     : {output.get('trade_status')}",
                (
                    f"  strategy         : {strategy.get('type')} {strategy.get('expiration')} "
                    f"{strategy.get('short_strike')}/{strategy.get('long_strike')}"
                ),
                f"  net credit       : {strategy.get('net_credit')}",
                f"  max loss         : {strategy.get('max_loss')}",
                (
                    f"  contracts        : {risk.get('recommended_contracts')} "
                    f"(risk passed: {risk.get('portfolio_risk_passed')})"
                ),
            ]
            reasons = output.get("rejection_reasons") or []
            if reasons:
                lines.append("  rejection_reasons:")
                lines.extend(f"    - {reason}" for reason in reasons)
            missing = output.get("missing_data") or []
            if missing:
                lines.append(f"  missing_data     : {', '.join(missing)}")
            text = "\n".join(lines)
        except Exception as exc:  # noqa: BLE001 - report any failure in the UI
            text = f"error: {exc}"
        self._show_if_current("analysis", generation, self._show_analysis, text)

    def _show_analysis(self, text: str) -> None:
        self.query_one("#analysis-result", Static).update(text)

    # -- journal -----------------------------------------------------------
    def _load_journal(self) -> None:
        generation = self._next_generation("journal")
        self._load_journal_worker(generation)

    @work(group="journal", exclusive=True, thread=True)
    def _load_journal_worker(self, generation: int) -> None:
        try:
            response = self._ipc.request(protocol.GetJournal())
            if response.kind != "JournalResult":
                raise MoocError(getattr(response, "message", "unexpected response"))
            report = response.report
            text = "\n".join(
                [
                    f"closed trades : {report.get('trades')}",
                    f"win rate      : {report.get('win_rate')}",
                    f"profit factor : {report.get('profit_factor')}",
                    f"expectancy    : {report.get('expectancy')}",
                    f"max drawdown  : {report.get('max_drawdown')}",
                    f"return on risk: {report.get('return_on_risk')}",
                    f"avg hold (d)  : {report.get('average_holding_period_days')}",
                ]
            )
        except Exception as exc:  # noqa: BLE001 - report any failure in the UI
            text = f"error: {exc}"
        self._show_if_current("journal", generation, self._show_journal, text)

    def _show_journal(self, text: str) -> None:
        self.query_one("#journal-result", Static).update(text)


def run(socket_path: Path, default_group: str = "") -> None:
    MoocApp(socket_path, default_group).run()
