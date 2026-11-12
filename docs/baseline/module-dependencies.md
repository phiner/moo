# P0.1 Module Dependencies & Call Chains (Baseline)

## 1. Dependency layers (high level)
- **CLI/TUI (`cli`, `tui`)** -> `config`, `policy`, `ipc.client/protocol`, `daemon.lifecycle`, and (CLI probes) `opend.*`, `services.*`, `storage.*` directly.
- **Daemon (`daemon.server`)** -> `ipc.protocol`, `services.option_data`, `services.trade`, `services.market_data`, `opend.client`, `config`, `daemon.lifecycle`.
- **Services** -> `opend.*` (SDK access), `domain.*`, `storage.*` (selectively), `config`, `policy`; some services are pure/domain-focused (`pricing`, `risk`, `scanner`, `selector`, `volatility`, `decision`, `journal` logic) while orchestration services perform I/O.
- **OpenD layer (`opend.*`)** -> `moomoo` SDK, `domain.*` (mapping), `opend.errors/values`.
- **Storage (`storage.*`)** -> `sqlite3`, `domain.*`, schema definitions.
- **Domain (`domain.*`)** -> stdlib/dataclasses/enums only (no SDK/IO).

## 2. Primary call chains

### Option/market/trade via daemon (IPC)
1. `tui.app` / IPC caller builds `protocol.*` request -> `ipc.client.IpcClient.request`.
2. `daemon.server.DaemonServer` receives frame -> `protocol.decode_request`.
3. Dispatch:
   - `TRADE_REQUESTS` -> `services.trade.TradeService.dispatch` (lock) -> `policy.resolve_trd_env` -> `opend.trade.*` -> `protocol.*Result`.
   - `MARKET_REQUESTS` -> `services.market_data.MarketDataService.dispatch` (lock) -> snapshot/volatility/events/analysis/journal handlers.
   - Others -> `services.option_data.OptionDataService.dispatch` (expirations/chain/combo/watchlist/underlying).
4. Response encoded and returned.

### Analysis (daemon)
`GetAnalysis` -> `MarketDataService._analysis` -> `services.analyze.analyze_symbol`:
- Inputs fetched via `opend.market.history_kline`, `opend.volatility.his_volatility`, `opend.quote.stock_snapshot`, `opend.events.earnings_calendar`, optional `opend.option.get_chain`/`snapshots`.
- Computation: `services.scanner.scan` (+ `services.volatility.summarize`), `services.selector.select_spread`, `services.pricing.*`, `services.risk.assess_trade`, `services.decision.build_output`.
- Persistence: `storage.db.open_db` + `services.recording.record_decision` -> `storage.repo` writes (best-effort, errors logged).

### Analysis (CLI direct path)
`cli._cmd_probe_analyze` -> load config/rules -> `OpendClient` direct -> optional funds via `opend.trade.get_funds` -> `analyze_symbol(..., account_equity=...)` -> local best-effort DB record -> stdout.
- Bypasses daemon context/IPC contract; behavior can differ from daemon `GetAnalysis`.

### Snapshot / volatility / events (market data)
- IPC: `GetStockSnapshot` -> `opend.quote.stock_snapshot` (freshness via `data_quality.realtime_max_age_sec`).
- IPC: `GetVolatility` -> `opend.volatility.his_volatility` -> `services.volatility.summarize`.
- IPC: `GetEvents` -> `opend.events.earnings_calendar` / `economic_calendar`.

### Monitor (CLI, current)
`cli._cmd_probe_monitor` -> `load_rules` -> `opend.trade.list_positions` -> `opend.option.snapshots` -> `services.monitor.cost_to_close`/`monitor_position` -> output (single-leg approximation, stale suppression). No IPC/service aggregation path.

### Journal
- IPC: `GetJournal` -> `storage.db.open_db` -> `storage.repo.journal_entries` -> `services.journal.report`.
- CLI: `probe journal` -> same storage/report path directly.

## 3. State ownership / boundaries
- **SDK contexts:** owned by daemon-held `OpendClient` for daemon paths; CLI probe commands create/connect/close their own client per invocation.
- **Serialization:** service-level locks in `OptionDataService`, `TradeService`, `MarketDataService` guard SDK calls; daemon also offloads blocking dispatch to threads.
- **Policy boundary:** `policy.resolve_trd_env` enforced in `TradeService` and CLI trade probes before SDK calls.
- **Storage boundary:** SQLite accessed by market/CLI/recording paths; schema managed via `storage.db.migrate` (DDL apply + `user_version` stamp).

## 4. Notable dependency gaps (P0-relevant)
- No shared `AnalysisContext` object flowing CLI/IPC/daemon/service; analysis inputs (account, rules version, snapshot refs) not centrally modeled.
- Decision persistence not injected as a required outcome of analysis response contract (daemon best-effort only).
- Quote validation/freshness logic partly in opend fetch + config thresholds, not a unified cross-instrument/multi-leg validation stage.
- Monitor logic duplicated/embedded in CLI rather than a reusable service + IPC contract.
