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


Request = Annotated[
    GetOptionExpirations | GetOptionChain | GetComboAnalysis,
    Field(discriminator="kind"),
]


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


Response = Annotated[
    OptionExpirationsResult | OptionChainResult | ComboAnalysisResult | ErrorResult,
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
