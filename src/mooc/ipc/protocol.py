"""Typed IPC request/response contract (externally tagged by ``kind``).

Input is validated at this boundary: codes are non-empty, leg actions are
restricted to BUY/SELL, leg quantities must be finite and strictly positive,
and combo leg counts are bounded.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# Upper bound for a single framed message (request or response).
MAX_FRAME_BYTES = 8 * 1024 * 1024

# Bounded combo size; multi-leg strategies are small (<= 6 legs in practice).
MAX_LEGS = 6


class Leg(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    code: str = Field(min_length=1)
    action: Literal["BUY", "SELL"] = "BUY"
    quantity: float = Field(default=1.0, gt=0)


# -- requests -------------------------------------------------------------
class GetOptionExpirations(BaseModel):
    kind: Literal["GetOptionExpirations"] = "GetOptionExpirations"
    request_id: int | None = None
    underlying: str = Field(min_length=1)


class GetOptionChain(BaseModel):
    kind: Literal["GetOptionChain"] = "GetOptionChain"
    request_id: int | None = None
    underlying: str = Field(min_length=1)
    start: str | None = None
    end: str | None = None
    option_type: Literal["ALL", "CALL", "PUT"] = "ALL"


class GetComboAnalysis(BaseModel):
    kind: Literal["GetComboAnalysis"] = "GetComboAnalysis"
    request_id: int | None = None
    legs: list[Leg] = Field(min_length=1, max_length=MAX_LEGS)


# -- watchlist requests (read-only) --------------------------------------
class GetWatchlistGroups(BaseModel):
    kind: Literal["GetWatchlistGroups"] = "GetWatchlistGroups"
    request_id: int | None = None


class GetWatchlistSummary(BaseModel):
    kind: Literal["GetWatchlistSummary"] = "GetWatchlistSummary"
    request_id: int | None = None
    group_name: str = Field(min_length=1)
    limit: int = Field(default=10, gt=0, le=200)


class GetWatchlistMembers(BaseModel):
    kind: Literal["GetWatchlistMembers"] = "GetWatchlistMembers"
    request_id: int | None = None
    group_name: str = Field(min_length=1)


class GetUnderlyingSummary(BaseModel):
    kind: Literal["GetUnderlyingSummary"] = "GetUnderlyingSummary"
    request_id: int | None = None
    code: str = Field(min_length=1)
    name: str = ""


# -- trade requests (read-only) ------------------------------------------
class GetAccounts(BaseModel):
    kind: Literal["GetAccounts"] = "GetAccounts"
    request_id: int | None = None
    trd_env: Literal["SIMULATE", "REAL"] | None = None


class GetFunds(BaseModel):
    kind: Literal["GetFunds"] = "GetFunds"
    request_id: int | None = None
    acc_id: int = Field(gt=0)
    trd_env: Literal["SIMULATE", "REAL"] | None = None
    currency: str | None = None


class GetPositions(BaseModel):
    kind: Literal["GetPositions"] = "GetPositions"
    request_id: int | None = None
    acc_id: int = Field(gt=0)
    trd_env: Literal["SIMULATE", "REAL"] | None = None
    code: str | None = None
    currency: str | None = None


class GetOrders(BaseModel):
    kind: Literal["GetOrders"] = "GetOrders"
    request_id: int | None = None
    acc_id: int = Field(gt=0)
    trd_env: Literal["SIMULATE", "REAL"] | None = None
    history: bool = False
    status_filter: list[str] = Field(default_factory=list)
    code: str | None = None
    start: str | None = None
    end: str | None = None


Request = Annotated[
    GetOptionExpirations
    | GetOptionChain
    | GetComboAnalysis
    | GetWatchlistGroups
    | GetWatchlistSummary
    | GetWatchlistMembers
    | GetUnderlyingSummary
    | GetAccounts
    | GetFunds
    | GetPositions
    | GetOrders,
    Field(discriminator="kind"),
]

# Request types handled by the trade service (routed separately by the daemon).
TRADE_REQUESTS = (GetAccounts, GetFunds, GetPositions, GetOrders)


# -- responses ------------------------------------------------------------
class Contract(BaseModel):
    code: str
    underlying: str
    expiry: str
    strike: float
    option_type: str
    multiplier: int


class OptionExpirationsResult(BaseModel):
    kind: Literal["OptionExpirationsResult"] = "OptionExpirationsResult"
    request_id: int | None = None
    dates: list[str]


class OptionChainResult(BaseModel):
    kind: Literal["OptionChainResult"] = "OptionChainResult"
    request_id: int | None = None
    underlying: str
    contracts: list[Contract]


class ComboAnalysisResult(BaseModel):
    kind: Literal["ComboAnalysisResult"] = "ComboAnalysisResult"
    request_id: int | None = None
    code: str
    name: str
    strategy: str
    bid1: float
    ask1: float
    max_profit: float
    max_loss: float
    breakeven: list[float]
    prob_profit: float
    delta: float
    theta: float


class ErrorResult(BaseModel):
    kind: Literal["Error"] = "Error"
    request_id: int | None = None
    message: str


# -- watchlist responses (read-only) -------------------------------------
class GroupDTO(BaseModel):
    name: str
    group_type: str


class WatchlistGroupsResult(BaseModel):
    kind: Literal["WatchlistGroupsResult"] = "WatchlistGroupsResult"
    request_id: int | None = None
    groups: list[GroupDTO]


class UnderlyingSummaryDTO(BaseModel):
    code: str
    name: str
    last_price: float | None
    expiry: str | None
    atm_strike: float | None
    call_bid: float | None
    call_ask: float | None
    put_bid: float | None
    put_ask: float | None


class WatchlistSummaryResult(BaseModel):
    kind: Literal["WatchlistSummaryResult"] = "WatchlistSummaryResult"
    request_id: int | None = None
    group_name: str
    items: list[UnderlyingSummaryDTO]


class MemberDTO(BaseModel):
    code: str
    name: str


class WatchlistMembersResult(BaseModel):
    kind: Literal["WatchlistMembersResult"] = "WatchlistMembersResult"
    request_id: int | None = None
    group_name: str
    total: int
    items: list[MemberDTO]


class UnderlyingSummaryResult(BaseModel):
    kind: Literal["UnderlyingSummaryResult"] = "UnderlyingSummaryResult"
    request_id: int | None = None
    item: UnderlyingSummaryDTO | None


# -- trade responses (read-only) -----------------------------------------
class AccountDTO(BaseModel):
    acc_id: int
    trd_env: str
    acc_type: str
    card_num: str
    security_firm: str
    sim_acc_type: str
    acc_status: str
    acc_role: str
    trdmarket_auth: list[str]


class AccountsResult(BaseModel):
    kind: Literal["AccountsResult"] = "AccountsResult"
    request_id: int | None = None
    accounts: list[AccountDTO]


class FundsDTO(BaseModel):
    acc_id: int
    trd_env: str
    currency: str
    cash: float | None
    total_assets: float | None
    securities_assets: float | None
    market_val: float | None
    available_funds: float | None
    frozen_cash: float | None
    power: float | None
    unrealized_pl: float | None
    realized_pl: float | None
    initial_margin: float | None
    maintenance_margin: float | None
    risk_level: str


class FundsResult(BaseModel):
    kind: Literal["FundsResult"] = "FundsResult"
    request_id: int | None = None
    acc_id: int
    funds: FundsDTO | None


class PositionDTO(BaseModel):
    code: str
    stock_name: str
    position_market: str
    qty: float
    can_sell_qty: float
    cost_price: float | None
    average_cost: float | None
    nominal_price: float | None
    market_val: float | None
    pl_ratio: float | None
    pl_val: float | None
    unrealized_pl: float | None
    realized_pl: float | None
    currency: str
    position_side: str
    strategy_type: str


class PositionsResult(BaseModel):
    kind: Literal["PositionsResult"] = "PositionsResult"
    request_id: int | None = None
    acc_id: int
    positions: list[PositionDTO]


class OrderDTO(BaseModel):
    code: str
    stock_name: str
    order_market: str
    trd_side: str
    order_type: str
    order_status: str
    order_id: str
    qty: float
    price: float
    dealt_qty: float
    dealt_avg_price: float
    create_time: str
    updated_time: str
    time_in_force: str
    currency: str
    remark: str
    last_err_msg: str


class OrdersResult(BaseModel):
    kind: Literal["OrdersResult"] = "OrdersResult"
    request_id: int | None = None
    acc_id: int
    orders: list[OrderDTO]


Response = Annotated[
    OptionExpirationsResult
    | OptionChainResult
    | ComboAnalysisResult
    | WatchlistGroupsResult
    | WatchlistSummaryResult
    | WatchlistMembersResult
    | UnderlyingSummaryResult
    | AccountsResult
    | FundsResult
    | PositionsResult
    | OrdersResult
    | ErrorResult,
    Field(discriminator="kind"),
]

_request_adapter: TypeAdapter = TypeAdapter(Request)
_response_adapter: TypeAdapter = TypeAdapter(Response)


def encode(message: BaseModel) -> bytes:
    """Serialize a request or response as one newline-terminated JSON frame."""
    frame = (message.model_dump_json() + "\n").encode("utf-8")
    if len(frame) > MAX_FRAME_BYTES:
        raise ValueError(f"frame exceeds MAX_FRAME_BYTES ({len(frame)} > {MAX_FRAME_BYTES})")
    return frame


def decode_request(line: bytes | str) -> Request:
    return _request_adapter.validate_json(line)


def decode_response(line: bytes | str) -> Response:
    return _response_adapter.validate_json(line)
