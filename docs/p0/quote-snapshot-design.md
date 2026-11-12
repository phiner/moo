# P0.3 Design: Quote Snapshot & Data Quality

## 1. Current implementation (baseline)
- **Domain:** `domain.market` defines `DataSource` (REALTIME/DELAYED/HISTORICAL/SIMULATED/UNKNOWN), `QuoteQuality`, `StockQuote`, `OptionSnapshot`, staleness helpers.
- **OpenD mapping:** `opend.quote.stock_snapshot` and `opend.option.snapshots` parse vendor `update_time` (US/Eastern) and build quality as `DataSource.REALTIME` with age-based staleness (`config.data_quality.realtime_max_age_sec`) and `missing_fields` when update_time absent. `opend.quote.last_prices/bid_ask` return unqualified prices.
- **Services:** `MarketDataService._snapshot` returns DTOs with quality; analysis fetches fresh snapshots/bars/vol/events per run but does not persist/link those exact inputs as snapshots. Selector requires bid/ask/delta presence for usable contracts but broader validation is distributed.
- **Storage:** `stock_quotes` and `option_quotes` tables store observed/source/is_stale and market fields (schema supports snapshot rows); `repo` upserts exist, but analysis path does not systematically write and reference snapshot ids for decisions.
- **Persistence:** critical analysis recording is best-effort in daemon path.

## 2. Gaps vs P0.3 requirements
- Data source/status not preserved from OpenD beyond inferred realtime/stale.
- No unified quote validation (bid/ask presence and sanity, negatives, bid>ask, cross-quote time skew, multi-leg consistency).
- Freshness thresholds not differentiated by instrument/context/multi-leg.
- Analysis results not reliably linked to persisted input snapshots; snapshot/decision persistence consistency not enforced.
- Persistence failures for critical artifacts may be hidden.

## 3. Proposed minimal design

### 3.1 Snapshot models and provenance
- Reuse/extend `StockQuote`/`OptionSnapshot`/`QuoteQuality` where possible:
  - keep `observed_at` (vendor/derived) and add/standardize `received_at` (local capture time)
  - capture `data_source`/market data status as accurately as OpenD provides (map to `DataSource`; retain raw status if available)
  - `quote_timestamp` semantics explicit (vendor update time) distinct from retrieval time
- Define snapshot identity for linkage:
  - DB row id or deterministic `snapshot_id` (e.g. code+observed_at+source hash) per quote/quote-set
  - optional aggregate ids: `market_snapshot_id` / `option_chain_snapshot_id` representing the set used in an analysis

### 3.2 Unified quote validation
Introduce a validation component/service (pure where possible) producing structured quality results:
- **Time:** missing timestamp, stale vs configurable thresholds, future timestamps, received vs quote skew, stock vs option time skew tolerance.
- **Price sanity:** missing bid/ask (and policy for last-only), negative/zero-invalid cases as applicable, bid>ask, extreme/obviously bad values (configurable/defensive).
- **Multi-leg:** each leg valid and fresh, timestamps within configured window, consistent source/status, reject/flag combinations that would imply false precision.
- Return explicit quality/status codes (e.g. `OK`, `STALE_DATA`, `INVALID_INPUT`/`INVALID_QUOTE`, `INSUFFICIENT_DATA`) consumable by analysis/selector/pricing.

### 3.3 Freshness configuration
- Keep `data_quality.realtime_max_age_sec`/`delayed_max_age_sec`; extend config (additive) if needed for stock vs option and multi-leg max skew without breaking existing keys.
- Centralize threshold selection (no scattered hardcoded seconds).

### 3.4 Persistence and linkage
- Persist relevant stock/option snapshots for analyses (dedupe via existing unique constraints/ids).
- Link `analysis_id` (from P0.2) to snapshot ids/refs in result and storage.
- Define consistency policy: if snapshot persistence required for traceability fails, mark analysis persistence/result accordingly (do not silently claim complete success). Non-critical logs may remain best-effort but must be labeled.
- Use additive schema changes + careful migration in `storage/db.py`/`schema.py` preserving existing rows.

### 3.5 Integration points
- `opend/quote.py`, `opend/option.py`: capture richer provenance fields and received time.
- `services/market_data.py`, `services/analyze.py`, `services/selector.py`: apply validation before use; propagate quality into `DecisionOutput`/rejection reasons/missing data.
- `storage/repo.py`: snapshot save/query helpers and analysis-snapshot linkage.
- IPC DTOs: expose quality/provenance needed by clients (additive).

## 4. Test plan (P0.3)
1. Realtime, delayed, historical, simulated, unknown source handling/mapping.
2. Expired/stale quotes flagged and blocked from normal realtime use.
3. Missing bid / missing ask / bid>ask / negative or invalid prices.
4. Stock-option timestamp mismatch and multi-leg timestamp spread too large.
5. Snapshot persistence success and linkage to analysis.
6. Snapshot save failure -> explicit persistence error/status.
7. Analysis record save failure -> explicit persistence error/status.
8. No false-precision strategy pricing from inconsistent multi-leg quotes.

## 5. Risks/notes
- OpenD field availability varies; unknown/unavailable fields must remain null/explicit, never fabricated.
- Storage growth: consider dedupe and storing only analysis-referenced snapshots/sets.
- Must not regress existing non-live behavior except to make quality/safety stricter and more explicit.
