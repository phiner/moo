"""Unified analysis orchestration for CLI and daemon (P0.2).

Single business entry: build context, compute decision, and persist with
explicit persistence status. OpenD/trade calls use the provided client.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime

from ..config import AppConfig
from ..domain.analysis import (
    AccountContext,
    AnalysisContext,
    AnalysisResultStatus,
    AnalysisRunResult,
    PersistenceStatus,
    new_analysis_id,
)
from ..domain.decision import DecisionOutput, TradeStatus
from ..domain.rules import StrategyRule
from ..ipc import protocol
from ..opend import trade as trade_api
from ..opend.client import OpendClient
from ..opend.errors import MoocError
from ..policy import resolve_trd_env
from ..storage import db as storage_db
from . import recording
from .analyze import analyze_symbol
from .rules import compute_rules_version, load_rules

logger = logging.getLogger(__name__)


def load_rules_with_version(config: AppConfig) -> tuple[list[StrategyRule], str | None, str | None]:
    try:
        rules = load_rules(config.rules.path)
    except MoocError as exc:
        return [], None, str(exc)
    return rules, compute_rules_version(rules, config.rules.path), None


def resolve_account_context(
    client: OpendClient,
    config: AppConfig,
    *,
    account_id: int | None = None,
    trd_env: str | None = None,
    currency: str | None = None,
) -> tuple[AccountContext | None, str | None]:
    """Resolve explicit account fields via policy-checked funds query. Never fabricates."""
    if account_id is None:
        return None, None
    resolved_env = resolve_trd_env(trd_env, config.trading)
    resolved_currency = (currency or config.trading.default_currency).upper()
    try:
        funds = trade_api.get_funds(client, resolved_env, account_id, currency=resolved_currency)
    except Exception as exc:  # noqa: BLE001
        return (
            AccountContext(account_id=account_id, trd_env=resolved_env, currency=resolved_currency),
            f"account funds unavailable: {exc}",
        )
    if funds is None:
        return (
            AccountContext(account_id=account_id, trd_env=resolved_env, currency=resolved_currency),
            "account funds unavailable: no data returned",
        )
    return (
        AccountContext(
            account_id=account_id,
            trd_env=resolved_env,
            currency=(getattr(funds, "currency", None) or resolved_currency),
            account_equity=getattr(funds, "total_assets", None),
            available_cash=getattr(funds, "cash", None),
            buying_power=getattr(funds, "power", None),
        ),
        None,
    )


def build_analysis_context(
    *,
    symbol: str,
    rules_version_value: str | None,
    account: AccountContext | None = None,
    entrypoint: str | None = None,
    requested_at: datetime | None = None,
    analysis_id: str | None = None,
) -> AnalysisContext:
    now = requested_at or datetime.now(UTC)
    return AnalysisContext(
        analysis_id=analysis_id or new_analysis_id(),
        symbol=symbol,
        requested_at=now,
        rules_version=rules_version_value,
        account=account,
        entrypoint=entrypoint,
    )


def _derive_analysis_status(
    output: DecisionOutput,
    *,
    rules_load_error: str | None = None,
    rules_version_value: str | None = None,
    account_requested: bool = False,
    account_note: str | None = None,
) -> str:
    if rules_load_error:
        return AnalysisResultStatus.RULE_NOT_CONFIGURED.value
    if account_note and account_requested:
        return AnalysisResultStatus.INSUFFICIENT_DATA.value
    risk = output.risk or {}
    raw_reasons = risk.get("reasons")
    reasons = [str(r).lower() for r in raw_reasons] if isinstance(raw_reasons, list) else []
    if (
        risk.get("portfolio_risk_passed") is False
        and risk.get("recommended_contracts") is None
        and any(
            "equity unavailable" in r or "account equity unavailable" in r or "undetermined" in r
            for r in reasons
        )
    ):
        return AnalysisResultStatus.INSUFFICIENT_DATA.value
    if (
        output.trade_status is TradeStatus.REJECTED
        and "no enabled strategy rules configured" in (output.rejection_reasons or [])
        and rules_version_value is None
    ):
        return AnalysisResultStatus.RULE_NOT_CONFIGURED.value
    return AnalysisResultStatus.OK.value


def _with_context(
    output: DecisionOutput, context: AnalysisContext, analysis_status: str
) -> DecisionOutput:
    return replace(
        output,
        analysis_id=context.analysis_id,
        requested_at=context.requested_at.isoformat(),
        rules_version=context.rules_version,
        analysis_status=analysis_status,
        account=context.account.to_dict() if context.account else None,
        context=context.to_dict(),
    )


def persist_analysis(output: DecisionOutput, config: AppConfig) -> PersistenceStatus:
    try:
        ts = output.requested_at or output.analysis_timestamp
        created_at = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        created_at = datetime.now(UTC)
    try:
        conn = storage_db.open_db(config.storage.path)
        try:
            recorded = recording.record_decision(conn, output, created_at=created_at)
        finally:
            conn.close()
        if recorded:
            return PersistenceStatus(status="saved")
        return PersistenceStatus(status="skipped", message="already recorded")
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to record decision: %s", exc)
        return PersistenceStatus(status="failed", message=str(exc))


def run_analysis(
    client: OpendClient,
    config: AppConfig,
    *,
    symbol: str,
    rules: list[StrategyRule] | None = None,
    rules_version_value: str | None = None,
    rules_load_error: str | None = None,
    account: AccountContext | None = None,
    account_note: str | None = None,
    account_requested: bool = False,
    entrypoint: str = "service",
    requested_at: datetime | None = None,
    analysis_id: str | None = None,
    persist: bool = True,
) -> AnalysisRunResult:
    """Unified analysis entry used by CLI and daemon."""
    if rules is None:
        rules, rules_version_value, rules_load_error = load_rules_with_version(config)
    elif rules_version_value is None and rules_load_error is None:
        try:
            rules_version_value = compute_rules_version(rules, config.rules.path)
        except Exception:  # noqa: BLE001
            rules_version_value = None

    context = build_analysis_context(
        symbol=symbol,
        rules_version_value=rules_version_value,
        account=account,
        entrypoint=entrypoint,
        requested_at=requested_at,
        analysis_id=analysis_id,
    )
    notes: list[str] = []
    if rules_load_error:
        notes.append(f"rules load error: {rules_load_error}")
    if account_note:
        notes.append(account_note)

    equity = account.account_equity if account and account.has_sizing_equity else None
    try:
        output = analyze_symbol(
            client,
            symbol,
            rules=rules,
            config=config,
            now=context.requested_at,
            account_equity=equity,
        )
    except Exception as exc:  # noqa: BLE001
        output = DecisionOutput(
            symbol=symbol,
            analysis_timestamp=context.requested_at.isoformat(),
            data_quality="unknown",
            recommended_action="no_trade",
            trade_status=TradeStatus.REJECTED,
            rejection_reasons=[f"analysis failed: {exc}"],
            missing_data=[],
        )
        analysis_status = AnalysisResultStatus.CALCULATION_ERROR.value
        output = _with_context(output, context, analysis_status)
        persistence = PersistenceStatus(status="not_attempted", message="analysis failed")
        return AnalysisRunResult(
            output=output,
            analysis_id=context.analysis_id,
            symbol=symbol,
            requested_at=context.requested_at.isoformat(),
            rules_version=context.rules_version,
            analysis_status=analysis_status,
            persistence=persistence,
            account=account.to_dict() if account else None,
            notes=notes + [str(exc)],
        )

    analysis_status = _derive_analysis_status(
        output,
        rules_load_error=rules_load_error,
        rules_version_value=rules_version_value,
        account_requested=account_requested,
        account_note=account_note,
    )
    output = _with_context(output, context, analysis_status)

    if persist:
        persistence = persist_analysis(output, config)
    else:
        persistence = PersistenceStatus(status="not_attempted")

    if persistence.status == "failed" and persistence.message:
        notes.append(f"persistence failed: {persistence.message}")

    return AnalysisRunResult(
        output=output,
        analysis_id=context.analysis_id,
        symbol=symbol,
        requested_at=context.requested_at.isoformat(),
        rules_version=context.rules_version,
        analysis_status=analysis_status,
        persistence=persistence,
        account=account.to_dict() if account else None,
        notes=notes,
    )


def analysis_result_to_ipc(
    run: AnalysisRunResult, *, request_id: int | None = None
) -> protocol.AnalysisResult:
    return protocol.AnalysisResult(
        request_id=request_id,
        output=run.output.to_dict(),
        analysis_id=run.analysis_id,
        symbol=run.symbol,
        requested_at=run.requested_at,
        rules_version=run.rules_version,
        analysis_status=run.analysis_status,
        persistence=run.persistence.to_dict(),
        account=run.account,
        notes=list(run.notes),
    )
