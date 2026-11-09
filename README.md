# mooc

US options data + trading client. Options-focused (no equities/ETF trading);
the self-selected watchlist is read only, to discover underlyings.
Python + the official `moomoo-api` SDK.

## Architecture

Daemon-mediated: `OpenD <- moomoo-api (SDK) -> daemon <- typed IPC (unix socket) -> TUI`.

- **daemon**: sole owner of the SDK connection; decodes typed IPC requests,
  dispatches to services, encodes responses.
- **TUI**: derived projection; all changes go through IPC requests.

## Status

- [x] S0 framework + SDK connectivity (`mooc doctor`)
- [x] S1 options data: expirations/chain/combo (SDK + IPC + daemon) + TUI (Chain + Strategy tabs)
- [x] Watchlist: self-selected groups -> multi-symbol ATM option summary (read-only) + TUI (Watchlist tab)
- [x] S2 trade (read-only): accounts/funds/positions/orders (SDK + IPC + daemon) + TUI (Account + Orders tabs)
- [ ] S3 trade (simulated orders)
- [ ] S4 screeners / ranks / events

## Install

```sh
uv sync --extra tui --extra dev
```

## Usage

```sh
uv run mooc doctor                       # SDK/OpenD connectivity
uv run mooc probe expirations US.AAPL     # list expirations (direct SDK)
uv run mooc probe chain US.AAPL --start 2026-11-18 --end 2026-11-18
uv run mooc probe combo '[{"code":"US.AAPL261118C270000","action":"BUY","quantity":1}]'

uv run mooc probe groups                          # self-selected groups
uv run mooc probe watchlist "My Group" [--limit 30]  # ATM option summary per underlying

uv run mooc probe accounts                       # list allowed trade accounts
uv run mooc probe funds --acc-id 123 [--currency USD]
uv run mooc probe positions --acc-id 123 [--code US.AAPL]
uv run mooc probe orders --acc-id 123 [--history] [--status FILLED_ALL]

uv run mooc daemon run                    # start daemon in the background
uv run mooc daemon status
uv run mooc daemon stop
uv run mooc tui                           # Textual client (Watchlist + Chain + Strategy + Account + Orders)
```

The TUI opens on the **Watchlist** tab: pick a self-selected group and see a
one-row-per-underlying ATM option summary (nearest expiry). Selecting a row opens
its full chain in the Chain tab, where you can also type any symbol manually.

The group's symbols (code + name) load in one call and are shown immediately;
the option data is rate limited (OpenD allows 10 chains per rolling 30 seconds),
so it is fetched 10 at a time and continues automatically as each window frees —
each row fills in as its data arrives.

Daemon logs are written to `~/.mooc/mooc.log` (or `$MOOC_RUNTIME_DIR/mooc.log`).

## Configuration

`mooc.toml` (see `mooc.example.toml`) plus `MOOC_*` env overrides.
Defaults: US market, USD currency, SIMULATE-only trading. `[ui] default_group`
selects the group the TUI opens on (empty = first custom group). Invalid values
fail fast with a clear error.

## Concurrency

SDK calls on the shared quote context are serialized by a lock; trade queries use
the same pattern on the trade context. The official Quote Object documentation
(<https://openapi.moomoo.com/moomoo-api-doc/en/quote/base.html>) documents the
connection lifecycle (create/close/start/stop) but gives no concurrency
guarantee for overlapping requests on one context, so requests are issued one at
a time. Contexts are always closed on shutdown.

## Validation

```sh
scripts/validate.sh                                   # ruff + mypy + pytest (non-live)
uv run python -m pytest -m live                       # live tests (require OpenD)
```
