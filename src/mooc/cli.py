"""``mooc`` command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from .config import load_config
from .daemon.lifecycle import daemon_paths, is_running, socket_is_live
from .domain.options import LegAction, OptionLeg
from .opend import events as events_api
from .opend import option as option_api
from .opend import quote as quote_api
from .opend import trade as trade_api
from .opend import volatility as vol_api
from .opend import watchlist as watchlist_api
from .opend.client import OpendClient
from .opend.errors import MoocError
from .policy import resolve_trd_env
from .services import monitor as monitor_svc
from .services import recording
from .services.analyze import analyze_symbol
from .services.journal import report as journal_report
from .services.rules import load_rules
from .services.volatility import summarize
from .storage import db as storage_db
from .storage import repo as storage_repo


# -- shared ---------------------------------------------------------------
def _parse_legs(raw: str) -> list[OptionLeg]:
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MoocError(f"invalid legs JSON: {exc}") from exc
    if not isinstance(items, list) or not items:
        raise MoocError("legs must be a non-empty JSON array")
    legs: list[OptionLeg] = []
    for index, item in enumerate(items):
        try:
            code = str(item["code"]).strip()
            action = LegAction(str(item.get("action", "BUY")).upper())
            quantity = float(item.get("quantity", 1.0))
        except (KeyError, TypeError, ValueError) as exc:
            raise MoocError(f"invalid leg #{index}: {exc}") from exc
        if not code:
            raise MoocError(f"invalid leg #{index}: empty code")
        if not math.isfinite(quantity) or quantity <= 0:
            raise MoocError(f"invalid leg #{index}: quantity must be a positive number")
        legs.append(OptionLeg(code=code, action=action, quantity=quantity))
    return legs


def _connected() -> OpendClient:
    """Unconnected client; a ``with`` block connects and closes it."""
    cfg = load_config()
    return OpendClient(host=cfg.opend.host, port=cfg.opend.port)


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


# -- doctor ---------------------------------------------------------------
def _cmd_doctor(_args: argparse.Namespace) -> int:
    cfg = load_config()
    client = OpendClient(host=cfg.opend.host, port=cfg.opend.port)
    try:
        client.check_tcp()
        print(f"OpenD reachable at {cfg.opend.host}:{cfg.opend.port}")
        client.connect()
        health = client.health()
        print(f"  server_ver : {health.server_ver}")
        print(f"  quote login: {health.qot_logined}")
        print(f"  trade login: {health.trd_logined}")
        print(f"  US market  : {health.market_us}")
        print(f"  HK market  : {health.market_hk}")
    finally:
        client.close()
    return 0


# -- probe (direct SDK) ---------------------------------------------------
def _cmd_probe_expirations(args: argparse.Namespace) -> int:
    with _connected() as client:
        dates = option_api.list_expirations(client, args.underlying)
    if args.json:
        print(json.dumps(dates, ensure_ascii=False))
    else:
        print(f"{args.underlying} expirations ({len(dates)}):")
        for value in dates:
            print(f"  {value}")
    return 0


def _cmd_probe_chain(args: argparse.Namespace) -> int:
    with _connected() as client:
        chain = option_api.get_chain(
            client, args.underlying, start=args.start, end=args.end, option_type=args.type
        )
    if args.json:
        payload = [
            {
                "code": c.code,
                "expiry": c.expiry.isoformat(),
                "strike": c.strike,
                "type": c.option_type.value,
                "multiplier": c.multiplier,
            }
            for c in chain.contracts
        ]
        print(
            json.dumps({"underlying": chain.underlying, "contracts": payload}, ensure_ascii=False)
        )
    else:
        print(f"{chain.underlying} chain: {len(chain.contracts)} contracts")
        for c in chain.contracts[:20]:
            print(f"  {c.code:<24} {c.expiry} {c.option_type.value:<4} {c.strike}")
    return 0


def _cmd_probe_combo(args: argparse.Namespace) -> int:
    legs = _parse_legs(args.legs)
    with _connected() as client:
        analysis = option_api.combo_analysis(client, legs)
    if args.json:
        print(
            json.dumps(
                {
                    "code": analysis.code,
                    "name": analysis.name,
                    "strategy": analysis.strategy,
                    "bid1": analysis.bid1,
                    "ask1": analysis.ask1,
                    "max_profit": analysis.max_profit,
                    "max_loss": analysis.max_loss,
                    "breakeven": analysis.breakeven,
                    "prob_profit": analysis.prob_profit,
                    "delta": analysis.delta,
                    "theta": analysis.theta,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"{analysis.name} ({analysis.strategy}) [{analysis.code}]")
        print(f"  combo bid/ask  : {analysis.bid1:.2f} / {analysis.ask1:.2f}")
        print(f"  max profit/loss: {analysis.max_profit:.2f} / {analysis.max_loss:.2f}")
        print(f"  breakeven      : {[round(x, 2) for x in analysis.breakeven]}")
        print(f"  prob of profit : {analysis.prob_profit:.2f}")
        print(f"  delta/theta    : {analysis.delta:.4f} / {analysis.theta:.4f}")
    return 0


# -- probe (watchlist, read-only, direct SDK) -----------------------------
def _cmd_probe_groups(args: argparse.Namespace) -> int:
    with _connected() as client:
        groups = watchlist_api.list_groups(client)
    if args.json:
        print(json.dumps([asdict(group) for group in groups], ensure_ascii=False, indent=2))
    else:
        print(f"groups: {len(groups)}")
        for group in groups:
            print(f"  {group.name} ({group.group_type})")
    return 0


def _cmd_probe_watchlist(args: argparse.Namespace) -> int:
    with _connected() as client:
        members = watchlist_api.list_group_members(client, args.group)
        summaries = watchlist_api.group_option_summaries(client, members, limit=args.limit)
    if args.json:
        print(json.dumps([asdict(s) for s in summaries], ensure_ascii=False, indent=2))
    else:
        print(f"{args.group}: {len(summaries)} underlyings")
        for summary in summaries:
            print(
                f"  {summary.code:<16} last={summary.last_price} exp={summary.expiry} "
                f"atm={summary.atm_strike} call={summary.call_bid}/{summary.call_ask} "
                f"put={summary.put_bid}/{summary.put_ask}"
            )
    return 0


# -- probe (market data, read-only, direct SDK) ---------------------------
def _cmd_probe_snapshot(args: argparse.Namespace) -> int:
    cfg = load_config()
    with _connected() as client:
        snapshots = quote_api.stock_snapshot(
            client,
            args.codes,
            now=datetime.now(UTC),
            max_age_seconds=cfg.data_quality.realtime_max_age_sec,
        )
    if args.json:
        payload = [
            {
                "code": q.code,
                "last": q.last,
                "bid": q.bid,
                "ask": q.ask,
                "volume": q.volume,
                "update_time": q.update_time.isoformat() if q.update_time else None,
                "source": q.quality.source.value,
                "observed_at": q.quality.observed_at.isoformat(),
                "is_stale": q.quality.is_stale,
                "missing_fields": list(q.quality.missing_fields),
            }
            for q in snapshots.values()
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"snapshots: {len(snapshots)}")
        for q in snapshots.values():
            flag = "STALE" if q.quality.is_stale else q.quality.source.value
            print(
                f"  {q.code:<16} last={q.last} bid={q.bid} ask={q.ask} "
                f"vol={q.volume} [{flag}] {q.quality.observed_at.isoformat()}"
            )
    return 0


def _cmd_probe_volatility(args: argparse.Namespace) -> int:
    end = date.today()
    begin = end - timedelta(days=args.history_days)
    with _connected() as client:
        points = vol_api.his_volatility(
            client, args.code, begin=begin.isoformat(), end=end.isoformat()
        )
    summary = summarize(points, lookback=args.lookback)
    if args.json:
        print(
            json.dumps(
                {
                    "code": args.code,
                    "iv": summary.iv,
                    "hv": summary.hv,
                    "iv_rank": summary.iv_rank,
                    "iv_percentile": summary.iv_percentile,
                    "iv_hv_diff": summary.iv_hv_diff,
                    "sample_size": len(points),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"{args.code} volatility ({len(points)} days, lookback {args.lookback})")
        print(f"  iv / hv        : {summary.iv} / {summary.hv}")
        print(f"  iv_rank        : {summary.iv_rank}")
        print(f"  iv_percentile  : {summary.iv_percentile}")
        print(f"  iv - hv        : {summary.iv_hv_diff}")
    return 0


def _cmd_probe_events(args: argparse.Namespace) -> int:
    now = datetime.now(UTC)
    begin = args.begin or date.today().isoformat()
    end = args.end or (date.fromisoformat(begin) + timedelta(days=7)).isoformat()
    with _connected() as client:
        collected = events_api.earnings_calendar(
            client, args.market, begin=begin, end=end, observed_at=now
        )
        if args.economic:
            collected += events_api.economic_calendar(client, begin=begin, end=end, observed_at=now)
    collected.sort(key=lambda event: event.event_datetime)
    if args.json:
        print(
            json.dumps(
                [asdict(event) for event in collected], ensure_ascii=False, indent=2, default=str
            )
        )
    else:
        print(f"events ({begin}..{end}): {len(collected)}")
        for event in collected:
            label = event.code or "-"
            print(f"  {event.event_datetime.date()} {event.event_type.value:<9} {label}")
    return 0


def _cmd_probe_analyze(args: argparse.Namespace) -> int:
    cfg = load_config()
    loaded = load_rules(cfg.rules.path)
    with _connected() as client:
        equity = None
        if args.acc_id:
            trd_env = resolve_trd_env(None, cfg.trading)
            funds = trade_api.get_funds(
                client, trd_env, args.acc_id, currency=cfg.trading.default_currency
            )
            if funds is not None:
                equity = funds.total_assets
        output = analyze_symbol(client, args.code, rules=loaded, config=cfg, account_equity=equity)
    recorded = False
    record_note = None
    try:
        conn = storage_db.open_db(cfg.storage.path)
        try:
            recorded = recording.record_decision(
                conn,
                output,
                created_at=datetime.fromisoformat(output.analysis_timestamp),
            )
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - best-effort like daemon
        record_note = f"recording failed: {exc}"
        logging.getLogger(__name__).warning("failed to record decision: %s", exc)

    if args.json:
        payload = output.to_dict()
        payload["recorded"] = recorded
        if record_note:
            payload["record_note"] = record_note
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{output.symbol} analysis @ {output.analysis_timestamp}")
        print(f"  data_quality     : {output.data_quality}")
        print(f"  market_regime    : {output.market_regime}")
        print(f"  volatility_regime: {output.volatility_regime}")
        print(f"  event_risk       : {output.event_risk}")
        print(f"  action           : {output.recommended_action}")
        print(f"  trade_status     : {output.trade_status.value}")
        if output.rejection_reasons:
            print("  rejection_reasons:")
            for reason in output.rejection_reasons:
                print(f"    - {reason}")
        if record_note:
            print(f"  (not recorded: {record_note})")
        elif recorded:
            print(f"  (recorded -> {cfg.storage.path})")
        else:
            print(f"  (already recorded -> {cfg.storage.path})")
    return 0


def _cmd_probe_journal(args: argparse.Namespace) -> int:
    cfg = load_config()
    path = Path(args.db).expanduser() if args.db else cfg.storage.path
    conn = storage_db.open_db(path)
    try:
        entries = storage_repo.journal_entries(conn, symbol=args.symbol)
    finally:
        conn.close()
    perf = journal_report(entries)
    if args.json:
        print(json.dumps(asdict(perf), ensure_ascii=False, indent=2))
    else:
        print(f"journal ({path}): {perf.trades} closed trades")
        print(f"  win rate     : {perf.win_rate}")
        print(f"  profit factor: {perf.profit_factor}")
        print(f"  expectancy   : {perf.expectancy}")
        print(f"  max drawdown : {perf.max_drawdown}")
        print(f"  return/risk  : {perf.return_on_risk}")
        print(f"  avg hold (d) : {perf.average_holding_period_days}")
    return 0


# -- probe (trade, read-only, direct SDK) ---------------------------------
def _cmd_probe_accounts(args: argparse.Namespace) -> int:
    cfg = load_config()
    trd_env = resolve_trd_env(args.trd_env, cfg.trading)
    with _connected() as client:
        accounts = trade_api.list_accounts(client, trd_env)
    if args.json:
        print(json.dumps([asdict(a) for a in accounts], ensure_ascii=False, indent=2))
    else:
        print(f"accounts ({trd_env}): {len(accounts)}")
        for a in accounts:
            print(
                f"  acc_id={a.acc_id} type={a.acc_type} firm={a.security_firm} "
                f"status={a.acc_status} auth={a.trdmarket_auth}"
            )
    return 0


def _cmd_probe_funds(args: argparse.Namespace) -> int:
    cfg = load_config()
    trd_env = resolve_trd_env(args.trd_env, cfg.trading)
    currency = args.currency or cfg.trading.default_currency
    with _connected() as client:
        funds = trade_api.get_funds(client, trd_env, args.acc_id, currency=currency)
    if funds is None:
        print(f"no funds returned for {trd_env}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(asdict(funds), ensure_ascii=False, indent=2))
    else:
        print(f"funds (account {funds.acc_id}, {funds.trd_env} {funds.currency})")
        print(f"  total_assets   : {funds.total_assets}")
        print(f"  cash           : {funds.cash}")
        print(f"  available_funds: {funds.available_funds}")
        print(f"  market_val     : {funds.market_val}")
        print(f"  unrealized_pl  : {funds.unrealized_pl}")
        print(f"  risk_level     : {funds.risk_level}")
    return 0


def _cmd_probe_positions(args: argparse.Namespace) -> int:
    cfg = load_config()
    trd_env = resolve_trd_env(args.trd_env, cfg.trading)
    currency = args.currency or cfg.trading.default_currency
    with _connected() as client:
        positions = trade_api.list_positions(
            client, trd_env, args.acc_id, code=args.code, currency=currency
        )
    if args.json:
        print(
            json.dumps(
                {
                    "acc_id": args.acc_id,
                    "trd_env": trd_env,
                    "positions": [asdict(p) for p in positions],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"positions (account {args.acc_id}, {trd_env}): {len(positions)}")
        for p in positions:
            print(
                f"  {p.code:<24} qty={p.qty:<6} avg={p.average_cost} "
                f"mv={p.market_val} pl={p.pl_val}"
            )
    return 0


def _cmd_probe_monitor(args: argparse.Namespace) -> int:
    cfg = load_config()
    trd_env = resolve_trd_env(args.trd_env, cfg.trading)
    currency = args.currency or cfg.trading.default_currency
    try:
        rules = [r for r in load_rules(cfg.rules.path) if r.enabled]
    except MoocError:
        rules = []
    rule = rules[0] if rules else None
    take_profit = None if rule is None else rule.take_profit_pct
    stop_multiple = None if rule is None else rule.stop_review_multiple
    time_exit = None if rule is None else rule.time_exit_dte

    with _connected() as client:
        positions = trade_api.list_positions(
            client, trd_env, args.acc_id, code=args.code, currency=currency
        )
        codes = [p.code for p in positions]
        now = datetime.now(UTC)
        snaps = (
            option_api.snapshots(
                client, codes, now=now, max_age_seconds=cfg.data_quality.realtime_max_age_sec
            )
            if codes
            else {}
        )
    rows = []
    for pos in positions:
        snap = snaps.get(pos.code)
        stale = bool(snap.quality.is_stale) if snap else False
        dte = _dte_from_code(pos.code)
        is_short = pos.qty < 0
        # monitor.cost_to_close: SELL => buy back at ask (close short), else sell at bid.
        close_action = "SELL" if is_short else "BUY"
        # Credit-style (take-profit/stop) signals apply to short/credit legs only;
        # for long legs pass 0 so price signals are suppressed but time-exit still runs.
        signal_credit = abs(pos.average_cost or 0.0) if is_short else 0.0
        tp = take_profit if isinstance(take_profit, (int, float)) else None
        stop_mult = stop_multiple if isinstance(stop_multiple, (int, float)) else None
        time_exit_dte = int(time_exit) if isinstance(time_exit, (int, float)) else None

        bid = None if (stale or snap is None) else snap.bid
        ask = None if (stale or snap is None) else snap.ask
        leg = monitor_svc.MonitoredLeg(
            code=pos.code,
            action=close_action,
            quantity=abs(pos.qty),
            bid=bid,
            ask=ask,
        )
        cost = None if stale else monitor_svc.cost_to_close([leg])
        signals = monitor_svc.monitor_position(
            legs=[leg],
            entry_credit=signal_credit,
            dte=dte,
            take_profit_pct=tp,
            stop_review_multiple=stop_mult,
            time_exit_dte=time_exit_dte,
        )
        credit_signals_applicable = is_short
        rows.append(
            {
                "code": pos.code,
                "qty": pos.qty,
                "side": pos.position_side,
                "entry_credit_per_share": abs(pos.average_cost or 0.0),
                "cost_to_close": cost,
                "signals": [{"kind": s.kind, "reason": s.reason} for s in signals],
                "dte": dte,
                "quote_stale": stale if snap else None,
                "signals_suppressed_stale": stale,
                "credit_signals_applicable": credit_signals_applicable,
                "monitor_note": "single-leg approximation",
            }
        )
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(f"monitor ({trd_env}, acc {args.acc_id}): {len(rows)} positions")
        for row in rows:
            raw = row["signals"]
            sigs = ",".join(s["kind"] for s in raw) if isinstance(raw, list) else "-"
            if not sigs:
                sigs = "-"
            suffix = " [stale:suppressed]" if row["signals_suppressed_stale"] else ""
            print(
                f"  {row['code']} qty={row['qty']:g} dte={row['dte']} "
                f"close_cost={row['cost_to_close']} signals={sigs}{suffix}"
            )
    return 0


def _dte_from_code(code: str) -> int | None:
    match = re.search(r"(\d{6})[CP]", code)
    if not match:
        return None
    try:
        expiry = datetime.strptime(match.group(1), "%y%m%d").date()
    except ValueError:
        return None
    return (expiry - date.today()).days


def _cmd_probe_orders(args: argparse.Namespace) -> int:
    cfg = load_config()
    trd_env = resolve_trd_env(args.trd_env, cfg.trading)
    with _connected() as client:
        orders = trade_api.list_orders(
            client,
            trd_env,
            args.acc_id,
            history=args.history,
            status_filter=args.status or [],
            code=args.code,
            start=args.start,
            end=args.end,
        )
    if args.json:
        print(
            json.dumps(
                {
                    "acc_id": args.acc_id,
                    "trd_env": trd_env,
                    "orders": [asdict(o) for o in orders],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        label = "history orders" if args.history else "orders"
        print(f"{label} (account {args.acc_id}, {trd_env}): {len(orders)}")
        for o in orders:
            print(
                f"  {o.order_id:<12} {o.code:<24} {o.trd_side:<4} "
                f"{o.order_status:<14} qty={o.qty} price={o.price}"
            )
    return 0


# -- daemon ---------------------------------------------------------------
def _cmd_daemon_serve(_args: argparse.Namespace) -> int:
    from .daemon.server import DaemonServer

    cfg = load_config()
    paths = daemon_paths()
    client = OpendClient(host=cfg.opend.host, port=cfg.opend.port)
    try:
        client.connect()
        asyncio.run(DaemonServer(paths, client, cfg.trading, cfg).serve_forever())
    except (MoocError, RuntimeError) as exc:
        logger = logging.getLogger(__name__)
        logger.exception("daemon failed")
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        client.close()
    return 0


def _cmd_daemon_run(_args: argparse.Namespace) -> int:
    paths = daemon_paths()
    paths.ensure_dir()
    if is_running(paths):
        print(f"daemon already running (pid {paths.readable_pid()})", file=sys.stderr)
        return 1

    command = [
        sys.executable,
        "-c",
        (
            "import argparse, logging; from mooc.cli import _cmd_daemon_serve; "
            "logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(name)s: %(message)s'); "
            "raise SystemExit(_cmd_daemon_serve(argparse.Namespace()))"
        ),
    ]
    with paths.log.open("ab") as log_file:
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as exc:
            print(f"[ERROR] failed to start daemon: {exc}", file=sys.stderr)
            return 1

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            print(f"[ERROR] daemon exited during startup; see {paths.log}", file=sys.stderr)
            _print_daemon_log_tail(paths.log)
            return 1
        if paths.readable_pid() == process.pid and socket_is_live(paths.socket):
            print(f"daemon running in background (pid {process.pid}, socket {paths.socket})")
            print(f"log: {paths.log}")
            return 0
        time.sleep(0.05)

    print(f"[ERROR] daemon startup timed out; see {paths.log}", file=sys.stderr)
    _stop_child(process)
    _print_daemon_log_tail(paths.log)
    return 1


def _stop_child(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _print_daemon_log_tail(path: Path, lines: int = 20) -> None:
    try:
        tail = path.read_text(errors="replace").splitlines()[-lines:]
    except OSError:
        return
    for line in tail:
        print(line, file=sys.stderr)


def _cmd_daemon_status(_args: argparse.Namespace) -> int:
    paths = daemon_paths()
    if is_running(paths):
        print(f"daemon running (pid {paths.readable_pid()}, socket {paths.socket})")
        return 0
    print("daemon stopped")
    return 1


def _cmd_daemon_stop(_args: argparse.Namespace) -> int:
    paths = daemon_paths()
    pid = paths.readable_pid()
    if pid is None or not is_running(paths):
        print("daemon not running")
        return 1
    os.kill(pid, signal.SIGTERM)
    print(f"sent SIGTERM to daemon (pid {pid})")
    return 0


# -- tui ------------------------------------------------------------------
def _cmd_tui(_args: argparse.Namespace) -> int:
    try:
        from .tui.app import run as run_tui
    except ImportError as exc:
        print(f"TUI unavailable ({exc}). Install with: uv sync --extra tui", file=sys.stderr)
        return 1
    cfg = load_config()
    run_tui(daemon_paths().socket, cfg.ui.default_group)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mooc", description="US options data + trading client")
    parser.add_argument("--log-level", default="info")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check SDK/OpenD connectivity")
    doctor.set_defaults(func=_cmd_doctor)

    probe = sub.add_parser("probe", help="read-only option data probes (direct SDK)")
    probe_sub = probe.add_subparsers(dest="probe", required=True)

    exp = probe_sub.add_parser("expirations", help="list option expirations")
    exp.add_argument("underlying")
    exp.add_argument("--json", action="store_true")
    exp.set_defaults(func=_cmd_probe_expirations)

    chain = probe_sub.add_parser("chain", help="fetch an option chain")
    chain.add_argument("underlying")
    chain.add_argument("--start")
    chain.add_argument("--end")
    chain.add_argument("--type", default="ALL", choices=["ALL", "CALL", "PUT"])
    chain.add_argument("--json", action="store_true")
    chain.set_defaults(func=_cmd_probe_chain)

    combo = probe_sub.add_parser("combo", help="combo bid/ask + P&L for legs JSON")
    combo.add_argument("legs")
    combo.add_argument("--json", action="store_true")
    combo.set_defaults(func=_cmd_probe_combo)

    snapshot = probe_sub.add_parser("snapshot", help="stock snapshots with freshness flags")
    snapshot.add_argument("codes", nargs="+")
    snapshot.add_argument("--json", action="store_true")
    snapshot.set_defaults(func=_cmd_probe_snapshot)

    vol = probe_sub.add_parser("volatility", help="IV/HV, IV Rank and IV Percentile")
    vol.add_argument("code")
    vol.add_argument("--history-days", type=_positive_int, default=364)
    vol.add_argument("--lookback", type=_positive_int, default=252)
    vol.add_argument("--json", action="store_true")
    vol.set_defaults(func=_cmd_probe_volatility)

    evts = probe_sub.add_parser("events", help="earnings (and optional economic) calendar")
    evts.add_argument("--market", default="US")
    evts.add_argument("--begin")
    evts.add_argument("--end")
    evts.add_argument("--economic", action="store_true", help="also include macro events")
    evts.add_argument("--json", action="store_true")
    evts.set_defaults(func=_cmd_probe_events)

    analysis = probe_sub.add_parser("analyze", help="full analysis (14.1 output) for a symbol")
    analysis.add_argument("code")
    analysis.add_argument("--acc-id", type=_positive_int, help="account id for risk sizing")
    analysis.add_argument("--json", action="store_true")
    analysis.set_defaults(func=_cmd_probe_analyze)

    journal = probe_sub.add_parser("journal", help="forward performance from the trade log")
    journal.add_argument("--symbol")
    journal.add_argument("--db", help="SQLite path (defaults to config storage.path)")
    journal.add_argument("--json", action="store_true")
    journal.set_defaults(func=_cmd_probe_journal)

    groups = probe_sub.add_parser("groups", help="list self-selected groups")
    groups.add_argument("--json", action="store_true")
    groups.set_defaults(func=_cmd_probe_groups)

    watch = probe_sub.add_parser("watchlist", help="option summary for a self-selected group")
    watch.add_argument("group")
    watch.add_argument("--limit", type=_positive_int, default=watchlist_api.DEFAULT_LIMIT)
    watch.add_argument("--json", action="store_true")
    watch.set_defaults(func=_cmd_probe_watchlist)

    accounts = probe_sub.add_parser("accounts", help="list trade accounts")
    accounts.add_argument("--trd-env")
    accounts.add_argument("--json", action="store_true")
    accounts.set_defaults(func=_cmd_probe_accounts)

    funds = probe_sub.add_parser("funds", help="account funds snapshot")
    funds.add_argument("--acc-id", type=_positive_int, required=True)
    funds.add_argument("--trd-env")
    funds.add_argument("--currency")
    funds.add_argument("--json", action="store_true")
    funds.set_defaults(func=_cmd_probe_funds)

    positions = probe_sub.add_parser("positions", help="list open positions")
    positions.add_argument("--acc-id", type=_positive_int, required=True)
    positions.add_argument("--trd-env")
    positions.add_argument("--code")
    positions.add_argument("--currency")
    positions.add_argument("--json", action="store_true")
    positions.set_defaults(func=_cmd_probe_positions)

    orders = probe_sub.add_parser("orders", help="list orders (current or --history)")
    orders.add_argument("--acc-id", type=_positive_int, required=True)
    orders.add_argument("--trd-env")
    orders.add_argument("--history", action="store_true")
    orders.add_argument("--status", action="append", help="order status filter (repeatable)")
    orders.add_argument("--code")
    orders.add_argument("--start")
    orders.add_argument("--end")
    orders.add_argument("--json", action="store_true")
    orders.set_defaults(func=_cmd_probe_orders)

    monitor = probe_sub.add_parser(
        "monitor", help="check open positions against exit rules (take-profit/stop/time)"
    )
    monitor.add_argument("--acc-id", type=_positive_int, required=True)
    monitor.add_argument("--trd-env")
    monitor.add_argument("--code")
    monitor.add_argument("--currency")
    monitor.add_argument("--json", action="store_true")
    monitor.set_defaults(func=_cmd_probe_monitor)

    daemon = sub.add_parser("daemon", help="manage the mooc daemon")
    daemon_sub = daemon.add_subparsers(dest="daemon", required=True)
    for name, fn in (
        ("run", _cmd_daemon_run),
        ("status", _cmd_daemon_status),
        ("stop", _cmd_daemon_stop),
    ):
        node = daemon_sub.add_parser(name)
        node.set_defaults(func=fn)

    tui = sub.add_parser("tui", help="launch the terminal UI")
    tui.set_defaults(func=_cmd_tui)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        return args.func(args)
    except MoocError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
