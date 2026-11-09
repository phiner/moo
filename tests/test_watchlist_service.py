from __future__ import annotations

import pandas as pd

from mooc.ipc import protocol
from mooc.services.option_data import OptionDataService


class _Ctx:
    def __init__(self, **frames: pd.DataFrame) -> None:
        self._frames = frames

    def get_user_security_group(self, group_type):
        return 0, self._frames["groups"]

    def get_user_security(self, group_name):
        return 0, self._frames["members"]

    def get_market_snapshot(self, codes):
        frame = self._frames["snapshot"]
        return 0, frame[frame["code"].isin(codes)]

    def get_option_expiration_date(self, code):
        return 0, self._frames["expiration"]

    def get_option_chain(self, code, **kwargs):
        return 0, self._frames["chain"]


class _Client:
    def __init__(self, ctx: _Ctx) -> None:
        self._ctx = ctx

    @property
    def quote_ctx(self):
        return self._ctx


def _summary_frames(codes: list[str]) -> dict[str, pd.DataFrame]:
    return {
        "members": pd.DataFrame(
            [{"code": code, "name": code, "stock_type": "STOCK"} for code in codes]
        ),
        "snapshot": pd.DataFrame(
            [
                {"code": code, "last_price": 100.0, "bid_price": 1.0, "ask_price": 1.1}
                for code in codes
            ]
        ),
        "expiration": pd.DataFrame({"strike_time": ["2099-01-15"]}),
        "chain": pd.DataFrame(
            [
                {
                    "code": "X",
                    "stock_owner": "X",
                    "strike_time": "2099-01-15",
                    "strike_price": 100.0,
                    "option_type": "CALL",
                    "lot_size": 100,
                }
            ]
        ),
    }


def test_dispatch_watchlist_groups():
    groups = pd.DataFrame([{"group_name": "Mine", "group_type": "CUSTOM"}])
    service = OptionDataService(_Client(_Ctx(groups=groups)))
    response = service.dispatch(protocol.GetWatchlistGroups(request_id=5))
    assert response.kind == "WatchlistGroupsResult"
    assert response.request_id == 5
    assert response.groups[0].name == "Mine"


def test_dispatch_watchlist_summary_applies_limit():
    frames = _summary_frames(["US.A", "US.B", "US.C"])
    service = OptionDataService(_Client(_Ctx(**frames)))
    response = service.dispatch(protocol.GetWatchlistSummary(group_name="Mine", limit=2))
    assert response.kind == "WatchlistSummaryResult"
    assert response.group_name == "Mine"
    assert [item.code for item in response.items] == ["US.A", "US.B"]


def test_dispatch_watchlist_members_returns_all():
    frames = _summary_frames(["US.A", "US.B", "US.C"])
    service = OptionDataService(_Client(_Ctx(**frames)))
    response = service.dispatch(protocol.GetWatchlistMembers(group_name="Mine"))
    assert response.kind == "WatchlistMembersResult"
    assert response.total == 3
    assert [item.code for item in response.items] == ["US.A", "US.B", "US.C"]


def test_dispatch_underlying_summary():
    frames = _summary_frames(["US.A"])
    service = OptionDataService(_Client(_Ctx(**frames)))
    response = service.dispatch(protocol.GetUnderlyingSummary(code="US.A", name="A Inc"))
    assert response.kind == "UnderlyingSummaryResult"
    assert response.item is not None
    assert response.item.code == "US.A"
