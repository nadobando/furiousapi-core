import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar, Generic, NoReturn

from lark import Lark, LarkError, UnexpectedCharacters, UnexpectedToken
from lark.exceptions import VisitError

from furiousapi.api.pagination import PaginationStrategyEnum
from furiousapi.core.types import TEntity
from furiousapi.rql.exceptions import (
    FuriousRQLSyntaxError,
    MismatchedBracketsError,
    MismatchedParenthesesError,
    SelectDotNotationError,
)
from furiousapi.rql.grammar import get_parser
from furiousapi.rql.transform import BaseRQLModelTransform

if TYPE_CHECKING:
    from furiousapi.api.pagination import PaginationStrategy


@dataclasses.dataclass
class TransformerConfig:
    allowed_sort: set[str] | None = None
    denied_sort: set[str] | None = None
    wildcard_fields: dict[str, list[str]] | None = None
    denied_fields: set[str] | None = None
    allowed_fields: set[str] | None = None
    allowed_filters: dict[str, set[str]] | None = None
    denied_filters: dict[str, set[str]] | None = None


class ModelRQL(Generic[TEntity]):
    __model__: type[TEntity]
    __parser__: ClassVar[Lark] = get_parser()
    __transformer__: type[BaseRQLModelTransform]
    __transformer_params__: TransformerConfig = TransformerConfig()

    RQL_ERRORS: ClassVar[dict[type[FuriousRQLSyntaxError] | str, list[str]]] = {
        MismatchedParenthesesError: [
            "eq(is_boolean,true);select(id,foreign[name]));sort(is_boolean)",
            "eq(is_boolean,true;select(id,foreign[name]);sort(is_boolean)",
        ],
        MismatchedBracketsError: [
            "select(id,foreign[name)",
        ],
        "UnexpectedSemicolon": ["eq(is_boolean,true);;select(id,foreign[name]);sort(is_boolean)"],
    }

    @classmethod
    def error_handling(cls, error: LarkError) -> NoReturn:
        if isinstance(error, UnexpectedToken):
            exc = error.match_examples(cls.__parser__.parse, cls.RQL_ERRORS)
            if exc and not isinstance(exc, str):
                raise exc(str(error.pos_in_stream))
            raise error

        if isinstance(error, UnexpectedCharacters):
            if error.token_history[0].type == "PROP_NO_DOT":
                left_context = error._context[: error.pos_in_stream]  # noqa: SLF001
                most_recent_function_start = left_context.rfind("(")
                pre_context = left_context[:most_recent_function_start].strip()
                if pre_context.endswith("select"):
                    raise SelectDotNotationError

        else:
            raise FuriousRQLSyntaxError(f"Parsing error: {error!s}")

        raise error

    @classmethod
    def parse(cls, query: str, pagination_type: "PaginationStrategy") -> Any:
        parsed_query = cls.__parser__.parse(query, on_error=cls.error_handling)
        if pagination_type == PaginationStrategyEnum.CURSOR:
            inject_sort_fields = True
        else:
            inject_sort_fields = False
        transformer = cls.__transformer__(
            cls.__model__,
            include_cursor_sort_fields=inject_sort_fields,
            **dataclasses.asdict(cls.__transformer_params__),
        )
        try:
            return transformer.transform(parsed_query)
        except VisitError as e:
            raise e.orig_exc from e
