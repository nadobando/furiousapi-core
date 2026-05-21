from __future__ import annotations

import copy
from abc import ABCMeta, abstractmethod
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Dict,
    Generic,
    Iterable,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from furiousapi.core.types import TEntity

if TYPE_CHECKING:
    from enum import Enum

    from furiousapi.api.pagination import PaginationStrategyEnum
    from furiousapi.api.responses import BulkResponseModel
    from furiousapi.db.pagination import BasePagination, Query


def inherit_config(
    self_config: Type[RepositoryConfig], parent_config: Type[RepositoryConfig], **namespace: Any
) -> Type[RepositoryConfig]:
    if not self_config:
        base_classes: Tuple[Type[RepositoryConfig], ...] = (parent_config,)
    elif self_config == parent_config:
        base_classes = (copy.deepcopy(self_config),)
    else:
        base_classes = self_config, parent_config

    return cast("Type[RepositoryConfig]", type(RepositoryConfig.__name__, base_classes, namespace))


class RepositoryConfig:
    paginators: ClassVar[Dict[PaginationStrategyEnum, BasePagination]] = {}


class RepositoryMeta(ABCMeta):
    def __new__(
        mcs: Type["RepositoryMeta"],
        name: str,
        bases: Tuple[Union[Type["BaseRepository"], Type]],
        namespace: dict,
    ) -> "RepositoryMeta":
        parents = [b for b in bases if isinstance(b, mcs)]
        if not parents:
            return super().__new__(mcs, name, bases, namespace)
        model = namespace["__orig_bases__"][0].__args__[0]
        if isinstance(model, TypeVar):
            return super().__new__(mcs, name, bases, namespace)
        new_namespace = {
            "__model__": model,
            **namespace,
        }
        return super().__new__(mcs, name, bases, new_namespace)


# todo: mypy issue
#  Free type variable expected in Generic[...]  [misc]
class BaseRepository(Generic[TEntity], metaclass=RepositoryMeta):

    if TYPE_CHECKING:
        __model__: Type[TEntity]
        __paginators__: Dict[PaginationStrategyEnum, BasePagination]

    def __init__(self):
        if not hasattr(self, "__paginators__"):
            self.__paginators__ = {}

        self.__init_paginators__()

    @abstractmethod
    def __primary_keys__(self): ...

    @abstractmethod
    async def get(
        self,
        identifiers: Union[int, str, Dict[str, Any], tuple],
        fields: Optional[Iterable["Enum"]] = None,
        *,
        should_error: bool = True,
    ) -> Optional[TEntity]: ...

    @abstractmethod
    async def add(self, entity: TEntity) -> TEntity: ...

    @abstractmethod
    async def patch(self, id_: Any, partial: TEntity, **kwargs) -> Optional[TEntity]:
        """Partial update: only fields explicitly set in `partial` are written.

        Mirrors HTTP PATCH semantics — omitted fields are preserved.
        """
        ...

    @abstractmethod
    async def replace(self, id_: Any, entity: TEntity, **kwargs) -> Optional[TEntity]:
        """Full replacement: all fields are written, including defaults for unset ones.

        Mirrors HTTP PUT semantics — the request is the new state of the resource.
        """
        ...

    async def update(self, id_: Any, entity: TEntity, **kwargs) -> Optional[TEntity]:
        """Deprecated. Alias of `patch()` — historical PATCH-semantics method.

        Use `patch(id_, partial)` for partial updates or `replace(id_, entity)`
        for full replacement. This shim will be removed in a future release.
        """
        import warnings

        warnings.warn(
            "BaseRepository.update() is deprecated; use patch() for partial updates "
            "or replace() for full replacement.",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self.patch(id_, entity, **kwargs)

    @abstractmethod
    async def delete(self, entity: Union[TEntity, str, int], **kwargs) -> None: ...

    @abstractmethod
    async def bulk_create(self, bulk: List[TEntity]) -> "BulkResponseModel": ...

    @abstractmethod
    async def bulk_delete(self, bulk: List[Union[TEntity, Any]]) -> List: ...

    @abstractmethod
    async def bulk_update(self, bulk: List[TEntity]) -> List: ...

    @abstractmethod
    def query(self, query: Any = None, *args, **kwargs) -> Optional[Query]: ...

    @abstractmethod
    async def execute(self, query: Any) -> Any: ...

    @abstractmethod
    def __init_paginators__(self) -> None: ...

    def get_paginator(self, mode: PaginationStrategyEnum) -> BasePagination:
        if not self.__paginators__:
            raise NotImplementedError(f"No paginators configured for {self.__class__.__name__}")

        paginator = self.__paginators__.get(mode)
        if not paginator:
            raise NotImplementedError(f"Pagination mode '{mode.name}' is not supported by {self.__class__.__name__}")
        return paginator
