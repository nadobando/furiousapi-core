from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from furiousapi.core.exceptions import FuriousError
from furiousapi.pydantic import PYDANTIC_V2

if TYPE_CHECKING:
    from furiousapi.api.pagination import PaginatedResponse
    from furiousapi.core.types import Query, Sorting, TEntity

logger = logging.getLogger(__name__)


class BasePagination:

    def get_limit(self, next_: Any) -> int:
        return self.validate_limit(next_)

    def validate_limit(self, requested_limit: int) -> int:
        return requested_limit

    @abstractmethod
    async def get_page(self, query: Query, limit: int, *args, **kwargs) -> PaginatedResponse[TEntity]:
        """
        Retrieves a page of data.

        Returns:
            A tuple containing a list of items and a boolean indicating if there are more pages.
        """


class OffsetPagination(BasePagination, ABC):
    """A pagination scheme that takes a user-specified limit and offset.

    This pagination scheme takes a user-specified limit and offset. It will
    retrieve up to the specified number of items, beginning at the specified
    offset.
    """


class PagePagination(OffsetPagination, ABC):
    def __init__(self, page_size: int) -> None:
        super().__init__()
        self._page_size = page_size

    def get_offset(self, page: int) -> int:
        return self.get_request_page(page) * self._page_size

    def get_request_page(self, page: int) -> int:
        return self.validate_page(page)

    @staticmethod
    def validate_page(requested_page: int) -> int:
        if requested_page is None:
            return 0

        if not isinstance(requested_page, int):
            raise FuriousError("Page must be an integer")

        if requested_page < 0:
            raise FuriousError("Page must be a positive integer")

        return requested_page

    def get_limit(self, _: str | None = None) -> int:
        return self._page_size


Cursor = tuple[Any, ...]


@dataclass
class CursorInfo:
    reversed: bool

    cursor: str | None
    cursor_arg: str | None

    limit: str | None
    limit_arg: str | None


class JSONLoad(Protocol):
    def __call__(self, data: str, *args, **kwargs) -> Any: ...


class BaseCursorPagination(BasePagination, ABC):
    __json_loads__: Callable
    __json_dumps__: Callable
    delimiter = "||"

    def __init__(
        self,
        id_fields: set[str],
        *args,
        validate_values: bool = True,
        **kwargs,
    ) -> None:
        self.id_fields = id_fields
        self._validate_values = validate_values

    @staticmethod
    def get_cursor_info(next_: str) -> CursorInfo:
        cursor = next_
        cursor_arg = None
        limit = None
        limit_arg = None
        reversed_ = False
        return CursorInfo(reversed_, cursor, cursor_arg, limit, limit_arg)

    @property
    def reversed(self) -> bool:
        return False

    def parse_cursor(self, cursor: str, field_orderings: list) -> tuple[tuple[str, Any], ...] | None:
        if cursor is None:
            return None
        parsed_cursor = self.decode_cursor(cursor)

        if len(parsed_cursor) != len(field_orderings):
            raise FuriousError("invalid_cursor.length")

        return tuple((field, value) for field, value in zip(field_orderings, parsed_cursor))

    def render_cursor(self, item: TEntity, column_fields: Iterable) -> str:
        if PYDANTIC_V2:
            cursor = tuple(self.__json_dumps__(getattr(item, field.value)).decode() for field in column_fields)
        else:
            cursor = tuple(self.__json_dumps__(getattr(item, field.value), default=str) for field in column_fields)
        return self.encode_cursor(cursor)

    def encode_cursor(self, cursor: tuple[str, ...]) -> str:
        return self.encode_value(self.delimiter.join(str(value) for value in cursor))

    def decode_cursor(self, cursor: str) -> list[str]:
        cursor = self.decode_value(cursor)
        return [self.__json_loads__(value) for value in cursor.split(self.delimiter)]

    def encode_value(self, value: Any) -> str:
        value = str(value)
        value = value.encode()
        value = base64.b64encode(value)
        return value.decode("ascii")

    @staticmethod
    def decode_value(value: str) -> str:
        encoded: bytes = value.encode()
        encoded += (3 - ((len(encoded) + 3) % 4)) * b"="  # Add back padding.
        return base64.b64decode(encoded).decode()

    def get_filter(self, field_orderings: list[tuple[str, str]], cursor: Cursor) -> Any:
        raise NotImplementedError

    def get_previous_clause(self, column_cursors: list[tuple[Any, Any, tuple[str, Any]]]) -> Any:
        raise NotImplementedError

    @staticmethod
    def _handle_nullable(column: Any, value: Any, *, is_nullable: bool) -> Any:
        raise NotImplementedError

    def _prepare_current_clause(self, column: Any, direction: Sorting, value: Any) -> Any:
        raise NotImplementedError

    def get_filter_clause(self, column_cursors: list[tuple[Any, Sorting, tuple[str, Any]]]) -> Any:
        raise NotImplementedError

    @abstractmethod
    def get_field_orderings(self, query: Any) -> list: ...


class BaseRelayPagination(BaseCursorPagination, ABC):
    def make_cursors(self, items: list[TEntity], field_orderings: list[Sorting]) -> tuple[str, ...]:
        return tuple(self.render_cursor(item, field_orderings) for item in items)
