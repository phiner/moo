"""Option data service: maps IPC requests to SDK calls and domain -> IPC DTOs.

SDK calls are serialized through a single lock. The official Quote Object
documentation (https://openapi.moomoo.com/moomoo-api-doc/en/quote/base.html)
documents connection lifecycle (create/close/start/stop) but gives no
concurrency guarantee for issuing overlapping requests on one context, so the
safe default is to issue them one at a time.
"""

from __future__ import annotations

import threading

from ..domain.options import LegAction, OptionLeg
from ..ipc import protocol
from ..opend import option
from ..opend.client import OpendClient
from ..opend.errors import MoocError


class OptionDataService:
    def __init__(self, client: OpendClient) -> None:
        self._client = client
        self._lock = threading.Lock()

    # -- request dispatch --------------------------------------------------
    def dispatch(self, request) -> protocol.Response:
        """Route one request to a handler. Never raises; errors become ``ErrorResult``."""
        request_id = getattr(request, "request_id", None)
        try:
            with self._lock:
                return self._dispatch_locked(request, request_id)
        except MoocError as exc:
            return protocol.ErrorResult(request_id=request_id, message=str(exc))
        except Exception as exc:  # noqa: BLE001 - boundary: never kill the loop
            return protocol.ErrorResult(request_id=request_id, message=f"internal error: {exc}")

    def _dispatch_locked(self, request, request_id: int | None) -> protocol.Response:
        if isinstance(request, protocol.GetOptionExpirations):
            return self._expirations(request)
        if isinstance(request, protocol.GetOptionChain):
            return self._chain(request)
        if isinstance(request, protocol.GetComboAnalysis):
            return self._combo(request)
        return protocol.ErrorResult(request_id=request_id, message="unknown request kind")

    # -- handlers ----------------------------------------------------------
    def _expirations(self, request: protocol.GetOptionExpirations) -> protocol.Response:
        dates = option.list_expirations(self._client, request.underlying)
        return protocol.OptionExpirationsResult(request_id=request.request_id, dates=dates)

    def _chain(self, request: protocol.GetOptionChain) -> protocol.Response:
        chain = option.get_chain(
            self._client,
            request.underlying,
            start=request.start,
            end=request.end,
            option_type=request.option_type,
        )
        contracts = [
            protocol.Contract(
                code=c.code,
                underlying=c.underlying,
                expiry=c.expiry.isoformat(),
                strike=c.strike,
                option_type=c.option_type.value,
                multiplier=c.multiplier,
            )
            for c in chain.contracts
        ]
        return protocol.OptionChainResult(
            request_id=request.request_id,
            underlying=chain.underlying,
            contracts=contracts,
        )

    def _combo(self, request: protocol.GetComboAnalysis) -> protocol.Response:
        legs = [
            OptionLeg(
                code=leg.code,
                action=LegAction(leg.action),
                quantity=float(leg.quantity),
            )
            for leg in request.legs
        ]
        analysis = option.combo_analysis(self._client, legs)
        return protocol.ComboAnalysisResult(
            request_id=request.request_id,
            code=analysis.code,
            name=analysis.name,
            strategy=analysis.strategy,
            bid1=analysis.bid1,
            ask1=analysis.ask1,
            max_profit=analysis.max_profit,
            max_loss=analysis.max_loss,
            breakeven=analysis.breakeven,
            prob_profit=analysis.prob_profit,
            delta=analysis.delta,
            theta=analysis.theta,
        )
