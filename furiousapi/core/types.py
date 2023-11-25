from enum import Enum
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from furiousapi.db.fields import SortableFieldEnum

TEntity = TypeVar("TEntity", bound=BaseModel)
TModelFields = TypeVar("TModelFields", bound=Enum)
TSortableFields = TypeVar("TSortableFields", bound="SortableFieldEnum")
TEntityFiltering = TypeVar("TEntityFiltering", bound=Enum)
