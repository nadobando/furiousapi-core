from enum import Enum
from typing import Literal, Tuple, TypeVar

from pydantic import BaseModel

TEntity = TypeVar("TEntity", bound=BaseModel)
TModelFields = TypeVar("TModelFields", bound=Enum)
SortingDirection = Literal["asc", "desc"]
Sorting = Tuple[str, SortingDirection]
Query = TypeVar("Query")
