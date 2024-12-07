from __future__ import annotations

import uuid
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Type,
    Union,
    get_args,
    get_origin,
)

from furiousapi.api.pagination import AllPaginationStrategies, PaginatedResponse
from furiousapi.core.types import TEntity, TModelFields
from furiousapi.db import BaseRepository, EntityNotFoundError, SortableFieldEnum

if TYPE_CHECKING:
    from enum import Enum

    from furiousapi.api.responses import BulkResponseModel


# TODO:
# mypy issue with Generic[TEntity]
class InMemoryDBRepository(BaseRepository[TEntity]):
    def __init__(self) -> None:
        self._store: Dict[Union[str, int, Dict[str, Any], tuple], TEntity] = {}

    async def get(
        self,
        identifiers: Union[int, str, Dict[str, Any], tuple],
        fields: Optional[Iterable[Enum]] = None,  # noqa: ARG002
        *,
        should_error: bool = True,
    ) -> Optional[TEntity]:
        if not self._store.get(identifiers) and should_error:
            raise EntityNotFoundError(self.__model__, identifiers)

        return self._store.get(identifiers)

    async def list(
        self,
        pagination: AllPaginationStrategies,  # noqa: ARG002
        fields: Optional[Iterable[TModelFields]] = None,  # noqa: ARG002
        sorting: Optional[List[SortableFieldEnum]] = None,  # noqa: ARG002
        filtering: Optional[TEntity] = None,  # noqa: ARG002
    ) -> PaginatedResponse[TEntity]:
        return PaginatedResponse[TEntity](total=len(self._store), items=list(self._store.values()), index=0, next=None)

    async def add(self, entity: TEntity) -> TEntity:

        if entity.id in self._store:  # type: ignore[attr-defined]
            raise ValueError(f"Key {entity.id} already exists")  # type: ignore[attr-defined]
        entity.id = str(uuid.uuid4())  # type: ignore[attr-defined]

        self._store[entity.id] = entity  # type: ignore[attr-defined]
        return entity

    async def update(self, id_: str, entity: TEntity, **kwargs) -> Optional[TEntity]:
        if id_ not in self._store:  # type: ignore[attr-defined]
            raise KeyError(f"Key {id_} does not exist")  # type: ignore[attr-defined]
        self._store[entity.id] = entity  # type: ignore[attr-defined]
        return entity

    async def delete(self, entity: Union[TEntity, str, int], **kwargs) -> None:
        if entity not in self._store:  # type: ignore[union-attr]
            raise KeyError(f"Key {entity} does not exist")  # type: ignore[union-attr]
        del self._store[entity]  # type: ignore[union-attr,arg-type]

    async def bulk_create(self, bulk: List[TEntity]) -> BulkResponseModel:  # type: ignore[empty-body]
        pass

    async def bulk_delete(self, bulk: List[Union[TEntity, Any]]) -> List:  # type: ignore[empty-body]
        pass

    async def bulk_update(self, bulk: List[TEntity]) -> List:  # type: ignore[empty-body]
        pass


def get_most_inner_class(annotation: Any) -> Type | None:
    """
    Recursively retrieves the most inner class from a type annotation.

    Args:
        annotation: The type annotation to inspect.

    Returns:
        The most inner class/type.
    """
    origin = get_origin(annotation)  # Extract the base of the type
    args = get_args(annotation)  # Extract the arguments (if any)

    if origin is None and not args:
        # Base case: This is the most inner type
        return annotation

    # Recursively process the arguments
    for arg in args:
        inner_class = get_most_inner_class(arg)
        if inner_class is not None:
            return inner_class

    return None
