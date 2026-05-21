from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Generic, List, Literal, Optional, Union

from furiousapi.core.types import TEntity
from furiousapi.pydantic import PYDANTIC_V2

if PYDANTIC_V2:
    from pydantic import BaseModel as GenericModel
else:
    from pydantic.generics import GenericModel

if TYPE_CHECKING:
    if PYDANTIC_V2:
        from pydantic.main import IncEx
    from pydantic.typing import AbstractSetIntStr, DictStrAny, MappingIntStrAny


class PaginatedResponse(GenericModel, Generic[TEntity]):
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
            by_alias: Optional[bool] = False,
            exclude_unset: bool = False,
            exclude_defaults: bool = False,
            exclude_none: bool = False,
            round_trip: bool = False,
            warnings: Union[Literal["none", "warn", "error"], bool] = False,
            fallback: Optional[Callable[[Any], Any]] = None,  # noqa: ARG002
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

        def dict(
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


PaginationStrategy = Union[PaginationStrategyEnum, Literal["cursor", "offset"]]
