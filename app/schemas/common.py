"""Shared response shapes."""

from decimal import Decimal
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

T = TypeVar("T")

Money = Annotated[
    Decimal,
    PlainSerializer(lambda value: float(value), return_type=float, when_used="json"),
]
Quantity = Annotated[
    Decimal,
    PlainSerializer(lambda value: float(value), return_type=float, when_used="json"),
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int


class Problem(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str
    request_id: str | None = None
    errors: list[dict[str, Any]] | None = None


class PageParams(BaseModel):
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


PROBLEMS: dict[int | str, dict[str, Any]] = {
    401: {"model": Problem, "description": "Missing or invalid credentials"},
    403: {"model": Problem, "description": "The token does not carry the required scope"},
    404: {"model": Problem, "description": "No record with that id"},
    409: {"model": Problem, "description": "The request conflicts with current state"},
    412: {"model": Problem, "description": "If-Match does not match the current version"},
    422: {"model": Problem, "description": "The request failed validation"},
    429: {"model": Problem, "description": "Rate limit exceeded"},
}
