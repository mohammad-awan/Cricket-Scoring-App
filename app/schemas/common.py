from __future__ import annotations
from typing import Generic, TypeVar
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


SchemaT = TypeVar("SchemaT")


class MasterDataQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    search: str | None = Field(default=None, max_length=100)
    include_archived: bool = False

    @field_validator("search", mode="before")
    @classmethod
    def normalize_search(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None

        return value


class PageResponse(BaseModel, Generic[SchemaT]):
    model_config = ConfigDict(from_attributes=True)

    items: list[SchemaT]
    page: int
    page_size: int
    total: int
    pages: int