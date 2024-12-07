from __future__ import annotations

from abc import abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, List, Literal, Optional, Union

from pydantic import ConfigDict, Field

from furiousapi.core.config import get_settings
from furiousapi.core.types import TEntity
from furiousapi.db.metaclasses import AllOptionalMeta
from furiousapi.db.models import FuriousModel
from furiousapi.pydantic import PYDANTIC_V2

if PYDANTIC_V2:
    from pydantic import BaseModel as GenericModel
else:
    from pydantic.generics import GenericModel

if TYPE_CHECKING:
    if PYDANTIC_V2:
        from pydantic.main import IncEx
    from pydantic.typing import AbstractSetIntStr, DictStrAny, MappingIntStrAny

SETTINGS = get_settings()


class PaginatedResponse(GenericModel, Generic[TEntity]):  # type: ignore[misc]
    total: Optional[int]
    items: List[TEntity]
    index: Optional[int]
    next: Optional[Union[str, int]] = None

    if PYDANTIC_V2:

        def model_dump(
            self,
            *,
            mode: Union[Literal["json", "python"], str] = "python",  # noqa: PYI051
            include: Optional[IncEx] = None,
            exclude: Optional[IncEx] = None,
            context: Optional[Any] = None,
            by_alias: bool = False,
            exclude_unset: bool = False,
            exclude_defaults: bool = False,
            exclude_none: bool = False,
            round_trip: bool = False,
            warnings: Union[bool, Literal["none", "warn", "error"]] = True,
            serialize_as_any: bool = False,
        ) -> dict[str, Any]:
            return super().model_dump(
                mode=mode,
                include=include,
                exclude=exclude,
                context=context,
                by_alias=by_alias,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
                exclude_none=exclude_none,
                round_trip=round_trip,
                warnings=warnings,
                serialize_as_any=serialize_as_any,
            )

    else:

        def dict(  # type: ignore[override]
            self,
            *,
            include: Optional[Union[AbstractSetIntStr, MappingIntStrAny]] = None,
            exclude: Optional[Union[AbstractSetIntStr, MappingIntStrAny]] = None,
            by_alias: bool = False,
            skip_defaults: Optional[bool] = None,
            exclude_unset: bool = False,
            exclude_defaults: bool = False,
            exclude_none: bool = True,
        ) -> DictStrAny:
            return super().dict(  # type: ignore[call-arg]
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
    if PYDANTIC_V2:
        model_config = ConfigDict(use_enum_values=True)
    else:

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
    next_: str | None = Field(None, alias="next", description="next record")

    @property
    def next(self) -> Optional[str]:
        return self.next_


AllPaginationStrategies = Union[CursorPaginationParams, OffsetPaginationParams]
