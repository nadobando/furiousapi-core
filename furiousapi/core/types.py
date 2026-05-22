from enum import Enum
from typing import Literal, TypeVar

from pydantic import BaseModel

TEntity = TypeVar("TEntity", bound=BaseModel)
TModelFields = TypeVar("TModelFields", bound=Enum)
SortingDirection = Literal["asc", "desc"]
Sorting = tuple[str, SortingDirection]
Query = TypeVar("Query")
