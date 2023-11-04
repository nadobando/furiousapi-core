import sys
from abc import ABCMeta, abstractmethod
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    Generic,
    Iterable,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from fastapi.params import Depends

from furiousapi.core.config import get_settings
from furiousapi.core.types import TEntity
from furiousapi.db import utils

if sys.version_info >= (3, 10):
    from typing import TypeAlias
else:
    from typing_extensions import TypeAlias

if TYPE_CHECKING:
    from enum import Enum

    from pydantic import BaseModel

    from furiousapi.api.pagination import AllPaginationStrategies
    from furiousapi.api.responses import BulkResponseModel
    from furiousapi.core.types import TModelFields
    from furiousapi.db.fields import SortableFieldEnum


class ModelMetaclass(Protocol):
    def __call__(self, model_name: str, bases: tuple, namespace: dict, **kwargs) -> Type["BaseModel"]: ...


ModelDependency: TypeAlias = Callable[
    [Type[TEntity]],
    Depends,
]


class RepositoryConfig:
    fields_include: ClassVar[Optional[Set[str]]] = None
    fields_exclude: ClassVar[Optional[Set[str]]] = None
    sort_include: ClassVar[Optional[Set[str]]] = None
    sort_exclude: ClassVar[Optional[Set[str]]] = None
    default_limit: ClassVar[int] = get_settings().pagination.default_size
    max_limit: ClassVar[int] = get_settings().pagination.max_size
    model_to_query: ClassVar[ModelDependency]
    filter_model: ClassVar[ModelMetaclass]


class RepositoryMeta(ABCMeta):
    def __new__(
        mcs: Type["RepositoryMeta"],  # noqa: N804
        name: str,
        bases: Tuple[Union[Type["BaseRepository"], Type]],
        namespace: dict,
    ) -> "RepositoryMeta":
        parents = [b for b in bases if isinstance(b, mcs)]
        if not parents:
            return super().__new__(mcs, name, bases, namespace)

        config = RepositoryConfig
        for base in reversed(bases):
            config = inherit_config(base.Config, config)

        config_from_namespace = namespace.get("Config", None)
        if config_from_namespace:
            config = inherit_config(config_from_namespace, config)

        namespace["Config"] = config
        model = namespace["__orig_bases__"][0].__args__[0]
        if isinstance(model, TypeVar):
            return super().__new__(mcs, name, bases, namespace)

        sort: Type["SortableFieldEnum"] = utils.get_model_sort_fields_enum(
            model, include=config.sort_include, exclude=config.sort_exclude
        )
        fields: Type[Enum] = utils.get_model_fields_enum(
            model, include=config.fields_include, exclude=config.fields_exclude
        )
        filtering = (
            config.filter_model is not None
            and config.filter_model(f"{model.__name__}Filtering", (model, *model.__bases__), {})
            or model
        )
        new_namespace = {
            "__model__": model,
            "__sort__": sort,
            "__fields__": fields,
            "__filtering__": filtering,
            **namespace,
        }
        return super().__new__(mcs, name, bases, new_namespace)


def inherit_config(
    self_config: Type[RepositoryConfig], parent_config: Type[RepositoryConfig], **namespace: Any
) -> Type[RepositoryConfig]:
    if not self_config:
        base_classes: Tuple[Type[RepositoryConfig], ...] = (parent_config,)
    elif self_config == parent_config:
        base_classes = (self_config,)
    else:
        base_classes = self_config, parent_config

    return cast(Type[RepositoryConfig], type(RepositoryConfig.__name__, base_classes, namespace))


# todo: mypy issue
#  Free type variable expected in Generic[...]  [misc]
class BaseRepository(Generic[TEntity], metaclass=RepositoryMeta):  # type: ignore[misc]
    if TYPE_CHECKING:
        __model__: Type[TEntity]
        __fields__: ClassVar[Type[Enum]]
        __sort__: ClassVar[Type[SortableFieldEnum]]
        __filtering__: ClassVar[Type[BaseModel]]

    Config = RepositoryConfig

    @abstractmethod
    async def get(
        self,
        identifiers: Union[int, str, Dict[str, Any], tuple],
        fields: Optional[Iterable["Enum"]] = None,
        *,
        should_error: bool = True,
    ) -> Optional[TEntity]: ...

    @abstractmethod
    async def list(
        self,
        pagination: "AllPaginationStrategies",
        fields: Optional[Iterable["TModelFields"]] = None,
        sorting: Optional[List["SortableFieldEnum"]] = None,
        filtering: Optional[TEntity] = None,
    ) -> Any: ...

    @abstractmethod
    async def add(self, entity: TEntity) -> TEntity: ...

    @abstractmethod
    async def update(self, entity: TEntity, **kwargs) -> Optional[TEntity]: ...

    @abstractmethod
    async def delete(self, entity: Union[TEntity, str, int], **kwargs) -> None: ...

    @abstractmethod
    async def bulk_create(self, bulk: List[TEntity]) -> "BulkResponseModel": ...

    @abstractmethod
    async def bulk_delete(self, bulk: List[Union[TEntity, Any]]) -> List: ...

    @abstractmethod
    async def bulk_update(self, bulk: List[TEntity]) -> List: ...
