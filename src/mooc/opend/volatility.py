"""Underlying IV/HV history access (read-only) built on ``moomoo-api``.

``get_option_underlying_his_volatility`` returns a daily IV/HV series (up to
~364 days, paged). IV Rank / IV Percentile are derived from this series by the
pure helpers in ``services.volatility``.
"""

from __future__ import annotations

from datetime import date

from ..domain.market import VolatilityPoint
from .client import OpendClient
from .values import require_ok as _require_ok
from .values import to_float as _num


def _parse_day(value) -> date:
    return date.fromisoformat(str(value)[:10])


def his_volatility(
    client: OpendClient,
    code: str,
    *,
    begin: str,
    end: str,
) -> list[VolatilityPoint]:
    """Return the daily IV/HV series for ``code`` over ``[begin, end]`` (ascending)."""
    points: list[VolatilityPoint] = []
    page = None
    while True:
        ret, data, page = client.quote_ctx.get_option_underlying_his_volatility(
            code, begin_time=begin, end_time=end, page_req_key=page
        )
        _require_ok("get_option_underlying_his_volatility", ret, data)
        for _, row in data.iterrows():
            points.append(
                VolatilityPoint(
                    day=_parse_day(row.get("time")),
                    iv=_num(row.get("iv")),
                    hv=_num(row.get("hv")),
                    underlying_price=_num(row.get("underlying_price")),
                )
            )
        if page is None:
            break
    return sorted(points, key=lambda point: point.day)
