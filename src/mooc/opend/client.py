"""Thin wrapper around the official ``moomoo-api`` SDK.

Owns the quote context used by the option data service (S1) and, lazily, the
US security trade context used by the trade service (S2). The trade context is
created on first use so a missing trade login never blocks quote-only work.
"""

from __future__ import annotations

import logging
import socket
from dataclasses import asdict, dataclass
from typing import Self

from .errors import MoocError, OpendRejected, OpendUnavailable

logger = logging.getLogger(__name__)

# ``ai_type`` requires SDK >= 10.4.6408.
SDK_MIN_VERSION = "10.4.6408"


@dataclass(frozen=True)
class HealthStatus:
    server_ver: str
    qot_logined: bool
    trd_logined: bool
    market_us: str
    market_hk: str

    def as_dict(self) -> dict:
        return asdict(self)


class OpendClient:
    """Owns the SDK contexts. One instance per process (the daemon)."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 11111,
        ai_type: int | None = 1,
    ) -> None:
        self.host = host
        self.port = port
        self._ai_type = ai_type
        self._quote_ctx = None
        self._trade_ctx = None

    # -- connectivity ------------------------------------------------------
    def check_tcp(self, timeout: float = 2.0) -> None:
        """Fail fast with a clear error if OpenD is not listening."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((self.host, self.port))
        except OSError as exc:
            raise OpendUnavailable(
                f"OpenD not reachable at {self.host}:{self.port}: {exc}"
            ) from exc
        finally:
            sock.close()

    def connect(self) -> Self:
        from moomoo import OpenQuoteContext

        self.check_tcp()
        kwargs: dict = {"host": self.host, "port": self.port}
        if self._ai_type is not None:
            kwargs["ai_type"] = self._ai_type
        try:
            self._quote_ctx = OpenQuoteContext(**kwargs)
        except Exception as exc:  # SDK raises assorted transport errors
            raise OpendUnavailable(f"failed to open quote context: {exc}") from exc
        logger.debug("quote context connected to %s:%s", self.host, self.port)
        return self

    def health(self) -> HealthStatus:
        from moomoo import RET_OK

        if self._quote_ctx is None:
            raise MoocError("connect() must be called before health()")
        ret, data = self._quote_ctx.get_global_state()
        if ret != RET_OK:
            raise OpendRejected("get_global_state", str(data))
        return HealthStatus(
            server_ver=str(data.get("server_ver", "?")),
            qot_logined=bool(data.get("qot_logined")),
            trd_logined=bool(data.get("trd_logined")),
            market_us=str(data.get("market_us", "?")),
            market_hk=str(data.get("market_hk", "?")),
        )

    @property
    def quote_ctx(self):
        if self._quote_ctx is None:
            raise MoocError("client is not connected")
        return self._quote_ctx

    @property
    def trade_ctx(self):
        """Lazily open the US security trade context on first access."""
        if self._trade_ctx is None:
            from moomoo import OpenSecTradeContext, TrdMarket

            kwargs: dict = {
                "filter_trdmarket": TrdMarket.US,
                "host": self.host,
                "port": self.port,
            }
            if self._ai_type is not None:
                kwargs["ai_type"] = self._ai_type
            try:
                self._trade_ctx = OpenSecTradeContext(**kwargs)
            except Exception as exc:  # SDK raises assorted transport errors
                raise OpendUnavailable(f"failed to open trade context: {exc}") from exc
            logger.debug("trade context connected to %s:%s", self.host, self.port)
        return self._trade_ctx

    def close(self) -> None:
        if self._quote_ctx is not None:
            try:
                self._quote_ctx.close()
            finally:
                self._quote_ctx = None
        if self._trade_ctx is not None:
            try:
                self._trade_ctx.close()
            finally:
                self._trade_ctx = None

    # -- context manager ---------------------------------------------------
    def __enter__(self) -> Self:
        return self.connect()

    def __exit__(self, *_exc) -> None:
        self.close()
