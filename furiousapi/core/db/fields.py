from enum import Enum, EnumMeta
from types import DynamicClassAttribute
from typing import Any, Dict, List, Optional

import pydantic.errors

from furiousapi.core.fields import SortingDirection


class GenerateByFieldEnum(str, Enum):
    NAME = "name"
    VALUE = "value"


# TODO: currently there are 2 bugs:
#  1. if we dont specify the operator the pagination runs forever
#      for example: +MyModel.my_field or -MyModel.my_field or ~MyModel.my_field
#  2. Enum members are singletons and may cause a bug with multi requests still need to check this
class SortableFieldsEnumMeta(EnumMeta):
    __default__: SortingDirection
    __delimiter__: str
    __examples_count__: int
    __examples_by__: GenerateByFieldEnum = GenerateByFieldEnum.NAME

    def __call__(cls, value: Any, names: Optional[List[str]] = None, **kwargs) -> Any:  # type: ignore[override]
        if names is None:
            field, _, direction = value.partition(cls.__delimiter__)
            instance: SortableFieldEnum = super().__call__(field)
            instance.__direction__ = direction and SortingDirection(direction) or cls.__default__
            return instance
        return super().__call__(value, names, **kwargs)

    def _generate_examples(cls, by_field: GenerateByFieldEnum = GenerateByFieldEnum.NAME) -> Dict[str, Dict[str, str]]:
        options: List[Any] = list(cls)
        examples = {}
        for i in range(min(len(options), cls.__examples_count__)):
            field_name = getattr(options[i], by_field.value)
            examples[str(-options[i])] = {
                "summary": f"order by  {field_name} {(-options[i]).direction}",
                "value": str(-options[i]),
            }
            examples[str(+options[i])] = {
                "summary": f"order by  {field_name} {(+options[i]).direction}",
                "value": str(+options[i]),
            }
        return examples

    @property
    def examples(cls) -> Dict[str, Any]:
        return cls._generate_examples(cls.__examples_by__)


class SortableFieldEnum(str, Enum, metaclass=SortableFieldsEnumMeta):
    __examples_count__: int = 3
    __examples_by__: GenerateByFieldEnum = GenerateByFieldEnum.NAME
    __default__ = SortingDirection.DESCENDING
    __delimiter__ = ":"
    __direction__: SortingDirection = SortingDirection.DESCENDING

    def __neg__(self) -> "SortableFieldEnum":
        self.__direction__ = SortingDirection.DESCENDING
        return self

    def __pos__(self) -> "SortableFieldEnum":
        self.__direction__ = SortingDirection.ASCENDING
        return self

    def __invert__(self) -> "SortableFieldEnum":
        if self.__direction__ == SortingDirection.ASCENDING:
            self.__neg__()
        else:
            self.__pos__()
        return self

    def __repr__(self) -> str:
        return f"<{self.name}: {self.direction}>"

    def __str__(self) -> str:
        return f"{self.name}:{self.direction}"

    @DynamicClassAttribute
    def direction(self) -> SortingDirection:
        return self.__direction__

    @classmethod
    def __get_validators__(cls) -> Any:
        yield cls.validate

    @classmethod
    def validate(cls, value: str) -> "SortableFieldEnum":
        field, _, direction = value.partition(":")
        possible_values = set(cls)
        if field not in possible_values:
            raise pydantic.errors.EnumMemberError(enum_values=possible_values)
        return cls(value)
