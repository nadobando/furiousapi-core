from enum import Enum
from typing import TypeVar

from pydantic import BaseModel

from furiousapi.db.fields import SortableFieldEnum

TEntity = TypeVar("TEntity", bound=BaseModel)
TModelFields = TypeVar("TModelFields", bound=Enum)
TSortableFields = TypeVar("TSortableFields", bound=SortableFieldEnum)
TEntityFiltering = TypeVar("TEntityFiltering", bound=Enum)
