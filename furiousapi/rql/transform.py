import datetime
import operator
from collections.abc import Callable
from typing import Any, Literal

from lark import Token
from lark.visitors import Transformer_InPlace
from pydantic import BaseModel

from furiousapi.pydantic._compat import PYDANTIC_V2
from furiousapi.rql.exceptions import (
    RQLFilterDeniedError,
    RQLFilterNotAllowedError,
    RQLSelectDeniedError,
    RQLSelectNotAllowedError,
    RQLSortDeniedError,
    RQLSortNotAllowedError,
)
from furiousapi.rql.grammar import COMPARATOR_MAPPING

if PYDANTIC_V2:
    from pydantic import TypeAdapter

    parse_datetime = TypeAdapter(datetime.datetime).validate_python
    parse_date = TypeAdapter(datetime.date).validate_python
    parse_time = TypeAdapter(datetime.time).validate_python
else:
    from pydantic.datetime_parse import parse_date, parse_datetime, parse_time

SelectedField = dict[str, None | dict[str, "SelectedField"]]


class BaseRQLModelTransform(Transformer_InPlace):
    model: type[BaseModel]

    def __init__(
        self,
        model: type[BaseModel],
        *,
        include_cursor_sort_fields: bool = False,
        allowed_sort: set[str] | None = None,
        denied_sort: set[str] | None = None,
        wildcard_fields: dict[str, list[str]] | None = None,
        denied_fields: set[str] | None = None,
        allowed_fields: set[str] | None = None,
        allowed_filters: dict[str, set[str]] | None = None,
        denied_filters: dict[str, set[str]] | None = None,
    ):
        super().__init__(visit_tokens=True)
        self.model = model

        self.include_cursor_sort_fields = include_cursor_sort_fields
        self.allowed_sort = allowed_sort or set()
        self.denied_sort = denied_sort or set()
        self.wildcard_fields = wildcard_fields or {}
        self.denied_fields = denied_fields or set()
        self.allowed_fields = allowed_fields or set()
        self.allowed_filters = allowed_filters or {}
        self.denied_filters = denied_filters or {}

        self.__sorting_fields__: list[tuple[str, Callable]] = []
        self.__filter_fields__: list[list] = []
        self.__selected_fields__: SelectedField = {}
        self.__distinct_fields__: list = []

    INT = int
    FLOAT = float
    UNQUOTED_VAL = str

    @staticmethod
    def TRUE(_: Token) -> Literal[True]:  # noqa: N802
        return True

    @staticmethod
    def FALSE(_: Token) -> Literal[False]:  # noqa: N802
        return False

    @staticmethod
    def TIME(s: Token) -> datetime.time:  # noqa: N802
        return parse_time(str(s))

    @staticmethod
    def DATE(s: Token) -> datetime.date:  # noqa: N802
        return parse_date(str(s))

    @staticmethod
    def DATETIME(s: Token) -> datetime.datetime:  # noqa: N802
        return parse_datetime(str(s))

    @staticmethod
    def QUOTED_VAL(val: Token) -> str:  # noqa: N802
        return val[1 : len(val) - 1]

    @staticmethod
    def STAR(_: Token) -> str:  # noqa: N802
        return "*"

    @staticmethod
    def CONST(c: Token) -> str | None:  # noqa: N802
        if c == "empty()":
            return ""
        if c.lower().startswith("null"):
            return None
        return None

    @staticmethod
    def PROP(p: Token) -> str:  # noqa: N802
        return p.value

    @staticmethod
    def PROP_NO_DOT(p: Token) -> str:  # noqa: N802
        return p.value

    @staticmethod
    def prop(p: list[str]) -> str:
        return p[0]

    @staticmethod
    def val(v: list[str | int | float | bool | None]) -> str | int | float | bool | None:
        return v[0]

    @staticmethod
    def value_tuple(t: list[str | int | float | bool | None]) -> list[str | int | float | bool | None]:
        return t

    @staticmethod
    def expr_term(e: list[list]) -> list:
        return e[0]

    @staticmethod
    def list_term(t: list[Token]) -> str:
        return t[0].value

    @staticmethod
    def logical_term(t: Token) -> Token:
        return t

    @staticmethod
    def comp_term(ct: list[Token]) -> str:
        op = COMPARATOR_MAPPING.get(ct[0].value)
        if not op:
            raise NotImplementedError(ct[0].value)
        return op

    @staticmethod
    def search_term(term: list[Token]) -> str:
        return term[0].value

    def sign_prop(self, expression: list[Token | str]) -> tuple[str, Callable]:
        direction, field = expression
        self.validate_sort_field(field)
        sign: Callable = operator.pos if direction in {None, "+"} else operator.neg
        return field, sign

    def comp(self, c: list) -> list:
        op, field, _ = c
        self.validate_filter_field(field, op)
        return c

    def listing(self, term: tuple[str, str, Any]) -> list:
        op, field, values = term[0], term[1], term[2:]
        self.validate_filter_field(field, op)
        return [COMPARATOR_MAPPING[op], field, values]

    def searching(self, expression: list) -> list:
        func, field, value = expression
        self.validate_filter_field(field, func)
        return expression

    # Logical
    @staticmethod
    def logical(expression: list[list[Any]]) -> list:
        return expression[0]

    @staticmethod
    def not_(expression: list[list]) -> list[Any | list[Any]]:
        return ["__not__", expression[0]]

    @staticmethod
    def and_(expression: list[list]) -> list[Any | list[Any]]:
        return ["__and__", expression]

    @staticmethod
    def or_(expression: list[list]) -> list[Any | list[Any]]:
        return ["__or__", expression]

    def selection(self, expression: list[dict | str]) -> SelectedField:
        result = {}
        for selection in expression:
            if isinstance(selection, dict):
                result.update(selection)
            else:
                result[selection] = None
        return result

    def nested_selection(self, t: Token) -> dict:
        parent = str(t[0])
        children = t[1:]
        parent_tree: dict = {parent: {}}
        for child in children:
            if isinstance(child, dict):
                parent_tree[parent].update(child)
            else:
                parent_tree[parent][child] = None

        return parent_tree

    def selectable_field(self, f: list[str | dict]) -> Any:
        return f[0]

    # Top Terms
    def select(self, selected: list[SelectedField]) -> list[SelectedField]:
        for selection in selected:
            self.__selected_fields__.update(selection)
        return selected

    def filter(self, f: list[Any]) -> list[Any]:
        if len(f) == 1 and f[0] is NotImplemented:
            return f
        self.__filter_fields__.extend(f)
        return f[0]

    def sort(self, sorting_fields: list[tuple[str, Callable]]) -> list[tuple[str, Callable]]:
        self.__sorting_fields__.extend(sorting_fields)
        return sorting_fields

    def distinct(self, d: list[str]) -> list[str]:
        self.__distinct_fields__.extend(d)
        return d

    # Validators
    def validate_filter_field(self, field: str, op: str) -> None:
        if self.allowed_filters:
            allowed_ops = self.allowed_filters.get(field)
            if allowed_ops is None or op not in allowed_ops:
                raise RQLFilterNotAllowedError(field, op, allowed_ops)
        if self.denied_filters and op in self.denied_filters.get(field, []):
            raise RQLFilterDeniedError(field, op)

    def validate_sort_field(self, field: str) -> None:
        if self.allowed_sort and field not in self.allowed_sort:
            raise RQLSortNotAllowedError(field)
        if self.denied_sort and field in self.denied_sort:
            raise RQLSortDeniedError(field)

    def validate_select_field(self, field: str) -> None:
        if self.allowed_fields and field not in self.allowed_fields:
            raise RQLSelectNotAllowedError(field)
        if self.denied_fields and field in self.denied_fields:
            raise RQLSelectDeniedError(field)

    def transform_wildcard(self, parent_prefix: str) -> list[str] | str:
        return self.wildcard_fields.get(parent_prefix, parent_prefix)

    def start(self, sta: list) -> Any:
        raise NotImplementedError


class RQLModelTransform(BaseRQLModelTransform):
    def start(self, _: list) -> dict[str, Any]:
        rql_object = {
            "fields": self.__selected_fields__,
            "sort": self.__sorting_fields__,
            "filter": self.__filter_fields__,
        }
        if self.__distinct_fields__:
            rql_object["distinct"] = self.__distinct_fields__
        return rql_object
