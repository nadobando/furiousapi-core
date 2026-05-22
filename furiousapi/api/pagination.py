from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, Literal, Union

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
    total: int | None
    items: list[TEntity]
    index: int | None
    next: str | int | None = None

    if PYDANTIC_V2:

        def model_dump(
            self,
            *,
            mode: Literal["json", "python"] | str = "python",  # noqa: PYI051
            include: IncEx | None = None,
            exclude: IncEx | None = None,
            context: Any | None = None,
            by_alias: bool | None = False,
            exclude_unset: bool = False,
            exclude_defaults: bool = False,
            exclude_none: bool = False,
            exclude_computed_fields: bool = False,
            round_trip: bool = False,
            warnings: Literal["none", "warn", "error"] | bool = False,
            fallback: Callable[[Any], Any] | None = None,  # noqa: ARG002
            serialize_as_any: bool = False,
            polymorphic_serialization: bool | None = None,
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
                exclude_computed_fields=exclude_computed_fields,
                round_trip=round_trip,
                warnings=warnings,
                serialize_as_any=serialize_as_any,
                polymorphic_serialization=polymorphic_serialization,
            )

    else:

        def dict(
            self,
            *,
            include: AbstractSetIntStr | MappingIntStrAny | None = None,
            exclude: AbstractSetIntStr | MappingIntStrAny | None = None,
            by_alias: bool = False,
            skip_defaults: bool | None = None,
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


PaginationStrategy = Union[PaginationStrategyEnum, Literal["cursor", "offset"]]  # noqa: UP007
