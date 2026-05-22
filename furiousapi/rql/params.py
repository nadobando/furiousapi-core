from collections.abc import Callable
from typing import Annotated, Any, Generic, TypeVar

from fastapi._compat import PYDANTIC_V2, Undefined
from fastapi.openapi.models import Example
from fastapi.params import Query, _Unset
from pydantic import BaseModel
from typing_extensions import deprecated

RQLStrModel = TypeVar("RQLStrModel")
if PYDANTIC_V2:
    from pydantic import AliasChoices, AliasPath

    class RQLStr(str, Generic[RQLStrModel]):
        __slots__ = ()

    class RQLQueryStr(Query):  # type: ignore[misc]
        def __init__(
            self,
            model: type[BaseModel] | None = None,
            default: Any = Undefined,
            *,
            default_factory: Callable[[], Any] | None = _Unset,
            annotation: Any | None = None,
            alias: str | None = None,
            alias_priority: int | None = _Unset,
            validation_alias: str | AliasPath | AliasChoices | None = None,
            serialization_alias: str | None = None,
            title: str | None = None,
            description: str | None = None,
            gt: float | None = None,
            ge: float | None = None,
            lt: float | None = None,
            le: float | None = None,
            min_length: int | None = None,
            max_length: int | None = None,
            pattern: str | None = None,
            regex: Annotated[
                str | None,
                deprecated("Deprecated in FastAPI 0.100.0 and Pydantic v2, use `pattern` instead."),
            ] = None,
            discriminator: str | None = None,
            strict: bool | None = _Unset,
            multiple_of: float | None = _Unset,
            allow_inf_nan: bool | None = _Unset,
            max_digits: int | None = _Unset,
            decimal_places: int | None = _Unset,
            examples: list[Any] | None = None,
            example: Annotated[
                Any | None,
                deprecated(
                    "Deprecated in OpenAPI 3.1.0 that now uses JSON Schema 2020-12, "
                    "although still supported. Use examples instead."
                ),
            ] = _Unset,
            openapi_examples: dict[str, Example] | None = None,
            deprecated: deprecated | str | bool | None = None,
            include_in_schema: bool = True,
            json_schema_extra: dict[str, Any] | None = None,
            **extra: Any,
        ):
            self.model = model
            _description: str = ""

            super().__init__(
                default,
                default_factory=default_factory,
                annotation=annotation,
                alias=alias,
                alias_priority=alias_priority,
                validation_alias=validation_alias,  # type: ignore[arg-type]
                serialization_alias=serialization_alias,
                title=title,
                description=description,
                gt=gt,
                ge=ge,
                lt=lt,
                le=le,
                min_length=min_length,
                max_length=max_length,
                pattern=pattern,
                regex=regex,
                discriminator=discriminator,
                strict=strict,
                multiple_of=multiple_of,
                allow_inf_nan=allow_inf_nan,
                max_digits=max_digits,
                decimal_places=decimal_places,
                examples=examples,
                example=example,
                openapi_examples=openapi_examples,
                deprecated=deprecated,
                include_in_schema=include_in_schema,
                json_schema_extra=json_schema_extra,
                **extra,
            )

else:

    class RQLStr(str):
        __slots__ = ()

    class RQLQueryStr(Query):  # type: ignore[misc]
        def __init__(
            self,
            model: type[BaseModel] | None = None,
            default: Any = Undefined,
            *,
            default_factory: Callable[[], Any] | None = _Unset,
            annotation: Any | None = None,
            alias: str | None = None,
            alias_priority: int | None = _Unset,
            validation_alias: str | None = None,
            serialization_alias: str | None = None,
            title: str | None = None,
            description: str | None = None,
            gt: float | None = None,
            ge: float | None = None,
            lt: float | None = None,
            le: float | None = None,
            min_length: int | None = None,
            max_length: int | None = None,
            pattern: str | None = None,
            regex: Annotated[
                str | None,
                deprecated("Deprecated in FastAPI 0.100.0 and Pydantic v2, use `pattern` instead."),
            ] = None,
            discriminator: str | None = None,
            strict: bool | None = _Unset,
            multiple_of: float | None = _Unset,
            allow_inf_nan: bool | None = _Unset,
            max_digits: int | None = _Unset,
            decimal_places: int | None = _Unset,
            examples: list[Any] | None = None,
            example: Annotated[
                Any | None,
                deprecated(
                    "Deprecated in OpenAPI 3.1.0 that now uses JSON Schema 2020-12, "
                    "although still supported. Use examples instead."
                ),
            ] = _Unset,
            openapi_examples: dict[str, Example] | None = None,
            deprecated: deprecated | str | bool | None = None,
            include_in_schema: bool = True,
            json_schema_extra: dict[str, Any] | None = None,
            **extra: Any,
        ):
            self.model = model
            super().__init__(
                default,
                default_factory=default_factory,
                annotation=annotation,
                alias=alias,
                alias_priority=alias_priority,
                validation_alias=validation_alias,
                serialization_alias=serialization_alias,
                title=title,
                description=description,
                gt=gt,
                ge=ge,
                lt=lt,
                le=le,
                min_length=min_length,
                max_length=max_length,
                pattern=pattern,
                regex=regex,
                discriminator=discriminator,
                strict=strict,
                multiple_of=multiple_of,
                allow_inf_nan=allow_inf_nan,
                max_digits=max_digits,
                decimal_places=decimal_places,
                examples=examples,
                example=example,
                openapi_examples=openapi_examples,
                deprecated=deprecated,
                include_in_schema=include_in_schema,
                json_schema_extra=json_schema_extra,
                **extra,
            )
