from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from mooc.config import AppConfig
from mooc.domain.analysis import AccountContext, new_analysis_id
from mooc.domain.rules import StrategyRule
from mooc.ipc import protocol
from mooc.services.analysis import (
    build_analysis_context,
    compute_rules_version,
    resolve_account_context,
    run_analysis,
)
from mooc.services.market_data import MarketDataService

NOW = datetime(2026, 11, 9, 20, 0, tzinfo=UTC)
EXPIRY = "2026-12-18"
EXPIRY_CODE = "261218"


def _bars_frame(count: int = 60) -> pd.DataFrame:
    start = datetime(2026, 1, 1)
    return pd.DataFrame(
        [
            {
                "time_key": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
                "open": 100.0 + i,
                "close": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "volume": 1000,
            }
            for i in range(count)
        ]
    )


class _QuoteCtx:
    def __init__(self, *, with_chain: bool = False) -> None:
        self._with_chain = with_chain

    def request_history_kline(self, code, **kwargs):
        return 0, _bars_frame(), None

    def get_option_underlying_his_volatility(self, code, **kwargs):
        frame = pd.DataFrame(
            [
                {"time": "2026-11-07", "iv": 30.0, "hv": 22.0, "underlying_price": 150.0},
                {"time": "2026-11-08", "iv": 55.0, "hv": 22.0, "underlying_price": 160.0},
            ]
        )
        return 0, frame, None

    def get_market_snapshot(self, codes):
        rows = []
        for code in codes:
            if code == "US.AAPL":
                rows.append(
                    {
                        "code": code,
                        "update_time": NOW.strftime("%Y-%m-%d %H:%M:%S"),
                        "last_price": 160.0,
                        "bid_price": 159.9,
                        "ask_price": 160.1,
                        "volume": 5000,
                    }
                )
            elif code in {"US.AAPL261218P95000", "US.AAPL261218P100000"}:
                bid = 1.0 if code.endswith("P95000") else 2.0
                delta = 0.15 if code.endswith("P95000") else 0.25
                rows.append(
                    {
                        "code": code,
                        "stock_owner": "US.AAPL",
                        "update_time": NOW.strftime("%Y-%m-%d %H:%M:%S"),
                        "last_price": bid,
                        "bid_price": bid,
                        "ask_price": bid + 0.1,
                        "volume": 100,
                        "option_delta": delta,
                        "option_implied_volatility": 0.3,
                        "option_open_interest": 500,
                    }
                )
        return 0, pd.DataFrame(rows)

    def get_earnings_calendar(self, market, begin_date=None, end_date=None, **kwargs):
        return 0, pd.DataFrame()

    def get_option_chain(self, code, **kwargs):
        if not self._with_chain:
            return 0, pd.DataFrame(
                columns=[
                    "code",
                    "stock_owner",
                    "strike_time",
                    "strike_price",
                    "option_type",
                    "lot_size",
                ]
            )
        return (
            0,
            pd.DataFrame(
                [
                    {
                        "code": f"US.AAPL{EXPIRY_CODE}P95000",
                        "stock_owner": "US.AAPL",
                        "strike_time": EXPIRY,
                        "strike_price": 95.0,
                        "option_type": "PUT",
                        "lot_size": 100,
                    },
                    {
                        "code": f"US.AAPL{EXPIRY_CODE}P100000",
                        "stock_owner": "US.AAPL",
                        "strike_time": EXPIRY,
                        "strike_price": 100.0,
                        "option_type": "PUT",
                        "lot_size": 100,
                    },
                ]
            ),
        )


class _TradeCtx:
    def __init__(self, funds_row):
        self._funds_row = funds_row

    def accinfo_query(self, **kwargs):
        if self._funds_row is None:
            return 0, pd.DataFrame()
        return 0, pd.DataFrame([self._funds_row])


class _Client:
    def __init__(self, *, with_chain: bool = False, funds_row=None):
        self.quote_ctx = _QuoteCtx(with_chain=with_chain)
        self._trade_ctx = _TradeCtx(funds_row)

    @property
    def trade_ctx(self):
        return self._trade_ctx


def _rule(**overrides) -> StrategyRule:
    base = {
        "name": "bull_put_credit_spread",
        "allowed_regimes": ("bullish", "strong_bullish"),
        "min_dte": 30,
        "max_dte": 45,
        "delta_min": 0.15,
        "delta_max": 0.25,
        "min_width": 5,
        "max_width": 5,
        "max_account_risk_pct": 0.25,
    }
    base.update(overrides)
    return StrategyRule(**base)


def test_analysis_context_builds_with_missing_account_fields():
    ctx = build_analysis_context(
        symbol="US.AAPL",
        rules_version_value="rv",
        account=AccountContext(account_id=7, account_equity=None, available_cash=None),
        entrypoint="cli",
        requested_at=NOW,
        analysis_id="aid-1",
    )
    assert ctx.analysis_id == "aid-1"
    assert ctx.symbol == "US.AAPL"
    assert ctx.rules_version == "rv"
    assert ctx.account is not None
    assert ctx.account.account_id == 7
    assert ctx.account.account_equity is None
    assert ctx.account.available_cash is None


def test_analysis_ids_unique_and_rules_version_deterministic():
    ids = {new_analysis_id() for _ in range(20)}
    assert len(ids) == 20
    r1 = compute_rules_version([_rule()], "rules")
    r2 = compute_rules_version([_rule()], "rules")
    r3 = compute_rules_version([_rule(max_account_risk_pct=0.10)], "rules")
    assert r1 == r2
    assert r1 != r3


def test_run_analysis_missing_account_keeps_market_analysis_but_no_position_sizing():
    cfg = AppConfig()
    run = run_analysis(
        _Client(with_chain=True),
        cfg,
        symbol="US.AAPL",
        rules=[_rule()],
        rules_version_value=compute_rules_version([_rule()], cfg.rules.path),
        account=AccountContext(account_id=1, account_equity=None, available_cash=12345.0),
        entrypoint="test",
        requested_at=NOW,
        analysis_id="aid-missing",
        persist=False,
    )
    out = run.output.to_dict()
    assert out["market_regime"] == "strong_bullish"
    assert out["volatility_regime"] == "high"
    assert out["event_risk"] == "low"
    assert out["strategy"]["type"] == "bull_put_credit_spread"
    assert out["risk"]["recommended_contracts"] is None
    assert out["risk"]["portfolio_risk_passed"] is False
    assert run.analysis_status == "INSUFFICIENT_DATA"
    assert run.analysis_id == "aid-missing"
    # account semantics preserved (cash != equity, equity not fabricated)
    assert run.account["available_cash"] == 12345.0
    assert run.account["account_equity"] is None


def test_run_analysis_with_equity_sets_sizing_and_ok_status():
    cfg = AppConfig()
    run = run_analysis(
        _Client(with_chain=True),
        cfg,
        symbol="US.AAPL",
        rules=[_rule()],
        rules_version_value=compute_rules_version([_rule()], cfg.rules.path),
        account=AccountContext(account_id=1, account_equity=10000.0, available_cash=9999.0),
        entrypoint="test",
        requested_at=NOW,
        analysis_id="aid-eq",
        persist=False,
    )
    out = run.output.to_dict()
    assert out["risk"]["recommended_contracts"] == 6
    assert out["risk"]["portfolio_risk_passed"] is True
    assert run.analysis_status == "OK"
    assert run.rules_version == compute_rules_version([_rule()], cfg.rules.path)
    assert out["analysis_id"] == "aid-eq"
    assert out["rules_version"] == run.rules_version


def test_resolve_account_context_does_not_conflate_equity_and_cash():
    cfg = AppConfig()
    funds = {
        "total_assets": 50000.0,
        "cash": 1200.0,
        "power": 8000.0,
        "currency": "USD",
    }
    acct, note = resolve_account_context(_Client(funds_row=funds), cfg, account_id=42)
    assert note is None
    assert acct is not None
    assert acct.account_equity == 50000.0
    assert acct.available_cash == 1200.0
    assert acct.buying_power == 8000.0
    assert acct.account_id == 42


def test_daemon_and_unified_entry_share_core_results_but_unique_ids(tmp_path):
    cfg = AppConfig()
    cfg = cfg.__class__(
        **{**cfg.__dict__, "storage": cfg.storage.__class__(path=tmp_path / "m.db")}
    )
    rules = [_rule()]
    rv = compute_rules_version(rules, cfg.rules.path)
    account = AccountContext(
        account_id=7,
        trd_env="SIMULATE",
        currency="USD",
        account_equity=10000.0,
        available_cash=10000.0,
        buying_power=10000.0,
    )
    funds = {"total_assets": 10000.0, "cash": 10000.0, "power": 10000.0, "currency": "USD"}
    client = _Client(with_chain=True, funds_row=funds)

    # Unified business entry (CLI-like usage of same service)
    run_cli = run_analysis(
        client,
        cfg,
        symbol="US.AAPL",
        rules=rules,
        rules_version_value=rv,
        account=account,
        entrypoint="cli",
        requested_at=NOW,
        persist=True,
    )

    # Daemon/IPC path via MarketDataService (resolves account from acc_id)
    svc = MarketDataService(client, cfg)
    svc._rules, svc._rules_version, svc._rules_load_error = rules, rv, None
    resp = svc.dispatch(
        protocol.GetAnalysis(
            code="US.AAPL", request_id=9, acc_id=7, trd_env="SIMULATE", currency="USD"
        )
    )
    assert resp.kind == "AnalysisResult"
    out_d = resp.output

    assert run_cli.analysis_id != resp.analysis_id
    assert run_cli.rules_version == resp.rules_version == rv
    assert run_cli.analysis_status == resp.analysis_status == "OK"
    # Core analysis/risk results consistent
    for key in (
        "symbol",
        "market_regime",
        "volatility_regime",
        "event_risk",
        "recommended_action",
        "trade_status",
    ):
        assert run_cli.output.to_dict()[key] == out_d[key]
    assert run_cli.output.to_dict()["strategy"] == out_d["strategy"]
    assert run_cli.output.to_dict()["risk"] == out_d["risk"]
    assert resp.persistence is not None and resp.persistence.get("status") in {"saved", "skipped"}
    assert run_cli.persistence.status in {"saved", "skipped"}


def test_persistence_failure_separated_from_analysis_status(tmp_path, monkeypatch):
    cfg = AppConfig()
    cfg = cfg.__class__(
        **{**cfg.__dict__, "storage": cfg.storage.__class__(path=tmp_path / "m.db")}
    )
    rules = [_rule()]
    run = run_analysis(
        _Client(with_chain=True),
        cfg,
        symbol="US.AAPL",
        rules=rules,
        rules_version_value=compute_rules_version(rules, cfg.rules.path),
        entrypoint="test",
        requested_at=NOW,
        analysis_id="aid-persist-fail",
        persist=False,
    )
    assert run.analysis_status == "OK" or run.analysis_status == "INSUFFICIENT_DATA"

    import mooc.services.analysis as analysis_mod

    monkeypatch.setattr(
        analysis_mod,
        "persist_analysis",
        lambda output, config: analysis_mod.PersistenceStatus(status="failed", message="disk full"),
    )
    run2 = analysis_mod.run_analysis(
        _Client(with_chain=True),
        cfg,
        symbol="US.AAPL",
        rules=rules,
        rules_version_value=compute_rules_version(rules, cfg.rules.path),
        entrypoint="test",
        requested_at=NOW,
        persist=True,
    )
    # analysis still produced, persistence explicitly failed
    assert run2.persistence.status == "failed"
    assert "disk full" in (run2.persistence.message or "")
    assert run2.output.trade_status is not None
    assert any("persistence failed" in n for n in run2.notes)


def test_ipc_old_request_and_new_response_compatibility():
    # Old/minimal request still valid
    req = protocol.decode_request(b'{"kind":"GetAnalysis","code":"US.AAPL","request_id":1}\n')
    assert isinstance(req, protocol.GetAnalysis)
    assert req.code == "US.AAPL"
    assert req.acc_id is None

    # New request with optional account fields
    req2 = protocol.GetAnalysis(code="US.AAPL", acc_id=7, trd_env="SIMULATE", currency="USD")
    back = protocol.decode_request(protocol.encode(req2))
    assert back.acc_id == 7
    assert back.trd_env == "SIMULATE"

    # New response fields are present and decodable; output remains primary payload
    resp = protocol.AnalysisResult(
        request_id=1,
        output={"symbol": "US.AAPL", "trade_status": "REJECTED"},
        analysis_id="aid",
        rules_version="rv",
        analysis_status="OK",
        persistence={"status": "saved"},
        account={"account_id": 7},
        notes=["n"],
    )
    decoded = protocol.decode_response(protocol.encode(resp))
    assert decoded.output["symbol"] == "US.AAPL"
    assert decoded.analysis_id == "aid"
    assert decoded.rules_version == "rv"
    assert decoded.persistence["status"] == "saved"


def test_invalid_input_and_rules_load_error_states(tmp_path):
    cfg = AppConfig()
    bad_rules = cfg.__class__(
        **{**cfg.__dict__, "rules": cfg.rules.__class__(path=tmp_path / "missing-rules-dir")}
    )
    run = run_analysis(
        _Client(with_chain=True),
        bad_rules,
        symbol="US.AAPL",
        entrypoint="test",
        requested_at=NOW,
        persist=False,
    )
    assert run.rules_version is None
    assert run.analysis_status == "RULE_NOT_CONFIGURED"
    assert run.output.to_dict()["trade_status"] == "REJECTED"
