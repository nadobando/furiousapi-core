import uuid
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Union

from furiousapi.api.pagination import AllPaginationStrategies, PaginatedResponse
from furiousapi.api.responses import BulkResponseModel
from furiousapi.core.types import TEntity, TModelFields
from furiousapi.db import BaseRepository, EntityNotFoundError, SortableFieldEnum


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

    async def update(self, entity: TEntity, **kwargs) -> Optional[TEntity]:
        if entity.id not in self._store:  # type: ignore[attr-defined]
            raise KeyError(f"Key {entity.id} does not exist")  # type: ignore[attr-defined]
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
