import uuid
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Union

from furiousapi.api.pagination import PaginatedResponse, PaginationStrategyEnum
from furiousapi.api.responses import BulkResponseModel
from furiousapi.core.types import Query, TEntity
from furiousapi.db import BaseRepository, EntityNotFoundError
from furiousapi.db.pagination import BasePagination


class InMemoryPaginator(BasePagination):

    def __init__(self, store: Dict[Union[str, int, Dict[str, Any], tuple], TEntity]):
        super().__init__()
        self._store = store

    async def get_page(self, *args, **kwargs) -> PaginatedResponse:
        return PaginatedResponse(total=len(self._store), items=list(self._store.values()), index=0, next=None)


class InMemoryDBRepository(BaseRepository[TEntity]):

    def __primary_keys__(self):
        return {"id"}

    def __init__(self) -> None:
        self._store: Dict[Union[str, int, Dict[str, Any], tuple], TEntity] = {}
        super().__init__()

    def __init_paginators__(self) -> None:
        paginator = InMemoryPaginator(self._store)
        self.__paginators__[PaginationStrategyEnum.CURSOR] = paginator
        self.__paginators__[PaginationStrategyEnum.OFFSET] = paginator

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

    def query(self, query: Any = None, *args, **kwargs) -> Optional[Query]:
        return query

    async def execute(self, _: Any) -> Any:
        return PaginatedResponse[TEntity](total=len(self._store), items=list(self._store.values()), index=0, next=None)
