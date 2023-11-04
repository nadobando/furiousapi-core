import base64
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Iterable,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    Type,
    Union,
)

from furiousapi.core.config import get_settings
from furiousapi.core.exceptions import FuriousError
from furiousapi.core.fields import SortingDirection
from furiousapi.core.types import TEntity
from furiousapi.db.fields import SortableFieldEnum

DEFAULT_PAGE_SIZE = get_settings().pagination.default_size
logger = logging.getLogger(__name__)


class BasePagination:
    def get_limit(self, next_: Any) -> int:
        return self.validate_limit(next_)

    def validate_limit(self, requested_limit: int) -> int:
        """
        Validates the requested limit and returns the limit value to use.

        Args:
            requested_limit (int or None): The requested limit value.

        Returns:
            int: The validated limit value.

        Raises:
            FuriousError: If the requested limit is invalid or exceeds the maximum limit.
        """
        return requested_limit


class PaginatorMixin(ABC):
    @abstractmethod
    async def get_page(self, *args, **kwargs) -> Any:
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
        """
        Validates the requested page and returns the page number to use.

        Args:
            requested_page (int or None): The requested page number.

        Returns:
            int: The validated page number.

        Raises:
            InvalidPageError: If the requested page is invalid.
        """
        if requested_page is None:
            return 0

        if not isinstance(requested_page, int):
            raise FuriousError("Page must be an integer")

        if requested_page < 0:
            raise FuriousError("Page must be a positive integer")

        return requested_page

    def get_limit(self, _: Optional[str] = None) -> int:
        return self._page_size


Cursor = Tuple[Any, ...]


@dataclass
class CursorInfo:
    reversed: bool

    cursor: Union[str, None]
    cursor_arg: Union[str, None]

    limit: Union[str, None]
    limit_arg: Union[str, None]


class JSONLoad(Protocol):
    def __call__(self, data: str, *args, **kwargs) -> Any: ...


class BaseCursorPagination(BasePagination, ABC):
    __json_loads__: Callable
    __json_dumps__: Callable
    #: The name of the query parameter to inspect for the cursor value.
    delimiter = "$$"

    def __init__(
        self,
        sort_enum: Type[SortableFieldEnum],
        id_fields: Set[str],
        sorting: List[SortableFieldEnum],
        *args,
        validate_values: bool = True,
        **kwargs,
    ) -> None:
        super().__init__()
        self.sort_enum = sort_enum
        self.sorting = sorting
        self.id_fields = id_fields
        self._validate_values = validate_values

    # There are a number of different cases that this covers in order to be backwards compatible with
    @staticmethod
    def get_cursor_info(next_: str) -> CursorInfo:
        cursor = next_
        cursor_arg = None

        limit = None
        limit_arg = None

        # Unambiguous cases where a cursor is provided.
        # if self.after_arg:

        # Ambiguous cases where limits are provided but not cursors
        # Relay sometimes sends both first and after, default to "first"
        # in keeping with the cursor precedence

        # legacy "cursor_arg" config cases always map to after/first
        reversed_ = False  #

        return CursorInfo(reversed_, cursor, cursor_arg, limit, limit_arg)

    @property
    def reversed(self) -> bool:
        return False

    def get_field_orderings(self) -> List[SortableFieldEnum]:
        if self.sorting is None:
            raise AssertionError("sorting must be defined when using cursor pagination")
        op = "__pos__" if self.sorting[-1].direction == SortingDirection.ASCENDING else "__neg__"

        missing_field_orderings = [
            getattr(self.sort_enum(id_field), op)()
            for id_field in self.id_fields
            if id_field not in frozenset(self.sorting)
        ]

        field_ordering = self.sorting + missing_field_orderings
        # if self.reversed:

        return field_ordering  # noqa: RET504

    def parse_cursor(
        self, cursor: str, field_orderings: List[SortableFieldEnum]
    ) -> Optional[Tuple[Tuple[str, Any], ...]]:
        if cursor is None:
            return None
        parsed_cursor = self.decode_cursor(cursor)

        if len(parsed_cursor) != len(field_orderings):
            raise FuriousError("invalid_cursor.length")

        return tuple((field, value) for field, value in zip(field_orderings, parsed_cursor))

    def render_cursor(self, item: TEntity, column_fields: Iterable[SortableFieldEnum]) -> str:
        cursor = tuple(self.__json_dumps__(getattr(item, field.value), default=str) for field in column_fields)
        return self.encode_cursor(cursor)

    def encode_cursor(self, cursor: Tuple[str, ...]) -> str:
        return self.encode_value(self.delimiter.join(str(value) for value in cursor))

    def decode_cursor(self, cursor: str) -> List[str]:
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

    def get_filter(self, field_orderings: List[SortableFieldEnum], cursor: Cursor) -> Any:
        raise NotImplementedError

    def get_previous_clause(self, column_cursors: List[Tuple[Any, SortingDirection, Tuple[str, Any]]]) -> Any:
        raise NotImplementedError

    @staticmethod
    def _handle_nullable(column: Any, value: Any, *, is_nullable: bool) -> Any:
        raise NotImplementedError

    def _prepare_current_clause(self, column: Any, direction: SortingDirection, value: Any) -> Any:
        raise NotImplementedError

    def get_filter_clause(self, column_cursors: List[Tuple[Any, SortingDirection, Tuple[str, Any]]]) -> Any:
        raise NotImplementedError


class BaseRelayPagination(BaseCursorPagination, ABC):
    def make_cursors(self, items: List[TEntity], field_orderings: List[SortableFieldEnum]) -> Tuple[str, ...]:
        return tuple(self.render_cursor(item, field_orderings) for item in items)
