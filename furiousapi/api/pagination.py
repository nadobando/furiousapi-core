from abc import abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, List, Literal, Optional, Union

from pydantic import Field
from pydantic.generics import GenericModel

from furiousapi.core.config import get_settings
from furiousapi.core.types import TEntity
from furiousapi.db.metaclasses import AllOptionalMeta
from furiousapi.db.models import FuriousModel

if TYPE_CHECKING:
    from pydantic.typing import AbstractSetIntStr, DictStrAny, MappingIntStrAny

SETTINGS = get_settings()


class PaginatedResponse(GenericModel, Generic[TEntity]):  # type: ignore[misc]
    total: Optional[int]
    items: List[TEntity]
    index: Optional[int]
    next: Optional[Union[str, int]]

    def dict(  # type: ignore[override]
        self,
        *,
        include: Optional[Union["AbstractSetIntStr", "MappingIntStrAny"]] = None,
        exclude: Optional[Union["AbstractSetIntStr", "MappingIntStrAny"]] = None,
        by_alias: bool = False,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = True,
    ) -> "DictStrAny":
        return super().dict(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            skip_defaults=skip_defaults,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )


class PaginationStrategyEnum(str, Enum):
    OFFSET = "offset"
    CURSOR = "cursor"


class BasePaginationParams(FuriousModel, metaclass=AllOptionalMeta):
    limit: int = Field(
        SETTINGS.pagination.default_size,
        le=SETTINGS.pagination.max_size,
        description="limit the result set",
    )

    class Config:
        use_enum_values = True

    @property
    @abstractmethod
    def next(self) -> Any: ...


class OffsetPaginationParams(BasePaginationParams):
    offset: Optional[int]
    pagination_type: Literal[PaginationStrategyEnum.OFFSET] = PaginationStrategyEnum.OFFSET

    @property
    def next(self) -> int:
        return self.offset or 0


class CursorPaginationParams(BasePaginationParams):
    pagination_type: Literal[PaginationStrategyEnum.CURSOR] = PaginationStrategyEnum.CURSOR
    next_: str = Field(alias="next", description="next record")

    @property
    def next(self) -> Optional[str]:
        return self.next_


AllPaginationStrategies = Union[CursorPaginationParams, OffsetPaginationParams]
