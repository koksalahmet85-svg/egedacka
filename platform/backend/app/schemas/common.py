from datetime import date
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Page(ApiModel, Generic[T]):
    items: list[T]
    total: int
    skip: int
    take: int


class PageParams(ApiModel):
    skip: int = Field(0, ge=0)
    take: int = Field(50, ge=1, le=200)


class Period(ApiModel):
    period: date = Field(description="Ayın herhangi bir günü; ayın ilk gününe yuvarlanır")
