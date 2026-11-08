# mooc

US options data + trading client. Pure options (no equities/watchlist/ETF).
Python + the official `moomoo-api` SDK.

## Architecture

Daemon-mediated: `OpenD <- moomoo-api (SDK) -> daemon <- typed IPC (unix socket) -> TUI`.

- **daemon**: sole owner of the SDK connection; decodes typed IPC requests,
  dispatches to services, encodes responses.
- **TUI**: derived projection; all changes go through IPC requests.

## Status

- [x] S0 framework + SDK connectivity (`mooc doctor`)
- [x] S1 options data: expirations/chain/combo (SDK + IPC + daemon) + TUI (Chain + Strategy tabs)
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

uv run mooc probe accounts                 # trade accounts (read-only)
uv run mooc probe funds [--currency USD]   # account funds snapshot
uv run mooc probe positions [--code US.AAPL]
uv run mooc probe orders [--history] [--status FILLED_ALL]

uv run mooc daemon run                    # start daemon (unix socket ~/.mooc/mooc.sock)
uv run mooc daemon status
uv run mooc daemon stop
uv run mooc tui                           # Textual client (Chain + Strategy + Account + Orders)
```

## Configuration

`mooc.toml` (see `mooc.example.toml`) plus `MOOC_*` env overrides.
Defaults: US market, USD currency, SIMULATE-only trading. Invalid values fail
fast with a clear error.

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
