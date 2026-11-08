"""``mooc`` command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import signal
import sys
from dataclasses import asdict

from .config import load_config
from .daemon.lifecycle import daemon_paths, is_running
from .domain.options import LegAction, OptionLeg
from .opend import option, trade
from .opend.client import OpendClient
from .opend.errors import MoocError
from .policy import resolve_trd_env


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
        dates = option.list_expirations(client, args.underlying)
    if args.json:
        print(json.dumps(dates, ensure_ascii=False))
    else:
        print(f"{args.underlying} expirations ({len(dates)}):")
        for value in dates:
            print(f"  {value}")
    return 0


def _cmd_probe_chain(args: argparse.Namespace) -> int:
    with _connected() as client:
        chain = option.get_chain(
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
        analysis = option.combo_analysis(client, legs)
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


# -- probe (trade, read-only, direct SDK) ---------------------------------
def _cmd_probe_accounts(args: argparse.Namespace) -> int:
    cfg = load_config()
    trd_env = resolve_trd_env(args.trd_env, cfg.trading)
    with _connected() as client:
        accounts = trade.list_accounts(client, trd_env)
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
        funds = trade.get_funds(client, trd_env, currency=currency)
    if funds is None:
        print(f"no funds returned for {trd_env}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(asdict(funds), ensure_ascii=False, indent=2))
    else:
        print(f"funds ({funds.trd_env} {funds.currency})")
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
        positions = trade.list_positions(client, trd_env, code=args.code, currency=currency)
    if args.json:
        print(json.dumps([asdict(p) for p in positions], ensure_ascii=False, indent=2))
    else:
        print(f"positions ({trd_env}): {len(positions)}")
        for p in positions:
            print(
                f"  {p.code:<24} qty={p.qty:<6} avg={p.average_cost} "
                f"mv={p.market_val} pl={p.pl_val}"
            )
    return 0


def _cmd_probe_orders(args: argparse.Namespace) -> int:
    cfg = load_config()
    trd_env = resolve_trd_env(args.trd_env, cfg.trading)
    with _connected() as client:
        orders = trade.list_orders(
            client,
            trd_env,
            history=args.history,
            status_filter=args.status or [],
            code=args.code,
            start=args.start,
            end=args.end,
        )
    if args.json:
        print(json.dumps([asdict(o) for o in orders], ensure_ascii=False, indent=2))
    else:
        label = "history orders" if args.history else "orders"
        print(f"{label} ({trd_env}): {len(orders)}")
        for o in orders:
            print(
                f"  {o.order_id:<12} {o.code:<24} {o.trd_side:<4} "
                f"{o.order_status:<14} qty={o.qty} price={o.price}"
            )
    return 0


# -- daemon ---------------------------------------------------------------
def _cmd_daemon_run(_args: argparse.Namespace) -> int:
    from .daemon.server import DaemonServer

    paths = daemon_paths()
    if is_running(paths):
        print(f"daemon already running (pid {paths.readable_pid()})", file=sys.stderr)
        return 1
    cfg = load_config()
    client = OpendClient(host=cfg.opend.host, port=cfg.opend.port).connect()
    server = DaemonServer(paths, client, cfg.trading)
    print(f"daemon starting; socket={paths.socket}")
    try:
        asyncio.run(server.serve_forever())
    except (MoocError, RuntimeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        client.close()
    return 0


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
    run_tui(daemon_paths().socket)
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

    accounts = probe_sub.add_parser("accounts", help="list trade accounts")
    accounts.add_argument("--trd-env")
    accounts.add_argument("--json", action="store_true")
    accounts.set_defaults(func=_cmd_probe_accounts)

    funds = probe_sub.add_parser("funds", help="account funds snapshot")
    funds.add_argument("--trd-env")
    funds.add_argument("--currency")
    funds.add_argument("--json", action="store_true")
    funds.set_defaults(func=_cmd_probe_funds)

    positions = probe_sub.add_parser("positions", help="list open positions")
    positions.add_argument("--trd-env")
    positions.add_argument("--code")
    positions.add_argument("--currency")
    positions.add_argument("--json", action="store_true")
    positions.set_defaults(func=_cmd_probe_positions)

    orders = probe_sub.add_parser("orders", help="list orders (current or --history)")
    orders.add_argument("--trd-env")
    orders.add_argument("--history", action="store_true")
    orders.add_argument("--status", action="append", help="order status filter (repeatable)")
    orders.add_argument("--code")
    orders.add_argument("--start")
    orders.add_argument("--end")
    orders.add_argument("--json", action="store_true")
    orders.set_defaults(func=_cmd_probe_orders)

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
