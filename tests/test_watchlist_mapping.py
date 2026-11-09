from __future__ import annotations

import pandas as pd

from mooc.opend import watchlist


class _FakeCtx:
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


class _FakeClient:
    def __init__(self, ctx: _FakeCtx) -> None:
        self._ctx = ctx

    @property
    def quote_ctx(self):
        return self._ctx


def _client(**frames: pd.DataFrame) -> _FakeClient:
    return _FakeClient(_FakeCtx(**frames))


def test_list_groups():
    groups = pd.DataFrame(
        [
            {"group_name": "Mine", "group_type": "CUSTOM"},
            {"group_name": "Tech", "group_type": "SYSTEM"},
        ]
    )
    result = watchlist.list_groups(_client(groups=groups))
    assert [(g.name, g.group_type) for g in result] == [("Mine", "CUSTOM"), ("Tech", "SYSTEM")]


def test_list_group_members_filters_non_underlyings():
    members = pd.DataFrame(
        [
            {"code": "US.AAPL", "name": "Apple", "stock_type": "STOCK"},
            {"code": "US.SPY", "name": "SPY", "stock_type": "ETF"},
            {"code": "US.AAPL990115C275000", "name": "AAPL CALL", "stock_type": "DRVT"},
        ]
    )
    result = watchlist.list_group_members(_client(members=members), "Mine")
    assert [m.code for m in result] == ["US.AAPL", "US.SPY"]


def test_group_option_summaries_picks_atm_and_quotes():
    members = pd.DataFrame([{"code": "US.AAPL", "name": "Apple", "stock_type": "STOCK"}])
    snapshot = pd.DataFrame(
        [
            {"code": "US.AAPL", "last_price": 275.0, "bid_price": 274.9, "ask_price": 275.1},
            {
                "code": "US.AAPL990115C275000",
                "last_price": 6.5,
                "bid_price": 6.4,
                "ask_price": 13.4,
            },
            {
                "code": "US.AAPL990115P275000",
                "last_price": 5.5,
                "bid_price": 5.0,
                "ask_price": 6.0,
            },
        ]
    )
    expiration = pd.DataFrame({"strike_time": ["2099-01-15", "2099-02-19"]})
    chain = pd.DataFrame(
        [
            {
                "code": "US.AAPL990115C275000",
                "stock_owner": "US.AAPL",
                "strike_time": "2099-01-15",
                "strike_price": 275.0,
                "option_type": "CALL",
                "lot_size": 100,
            },
            {
                "code": "US.AAPL990115P275000",
                "stock_owner": "US.AAPL",
                "strike_time": "2099-01-15",
                "strike_price": 275.0,
                "option_type": "PUT",
                "lot_size": 100,
            },
            {
                "code": "US.AAPL990115C300000",
                "stock_owner": "US.AAPL",
                "strike_time": "2099-01-15",
                "strike_price": 300.0,
                "option_type": "CALL",
                "lot_size": 100,
            },
        ]
    )
    members_list = watchlist.list_group_members(_client(members=members), "Mine")
    client = _client(members=members, snapshot=snapshot, expiration=expiration, chain=chain)
    summary = watchlist.group_option_summaries(client, members_list)[0]
    assert summary.code == "US.AAPL"
    assert summary.last_price == 275.0
    assert summary.expiry == "2099-01-15"
    assert summary.atm_strike == 275.0
    assert (summary.call_bid, summary.call_ask) == (6.4, 13.4)
    assert (summary.put_bid, summary.put_ask) == (5.0, 6.0)


def test_group_option_summaries_without_chain_stays_blank():
    members = pd.DataFrame([{"code": "US.NOOPT", "name": "No Options", "stock_type": "STOCK"}])
    snapshot = pd.DataFrame(
        [{"code": "US.NOOPT", "last_price": 10.0, "bid_price": 9.9, "ask_price": 10.1}]
    )
    expiration = pd.DataFrame({"strike_time": []})
    members_list = watchlist.list_group_members(_client(members=members), "Mine")
    client = _client(snapshot=snapshot, expiration=expiration)
    summary = watchlist.group_option_summaries(client, members_list)[0]
    assert summary.expiry is None
    assert summary.atm_strike is None
    assert summary.call_bid is None
