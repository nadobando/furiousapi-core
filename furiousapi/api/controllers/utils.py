from __future__ import annotations

import re
from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from furiousapi.api.controllers import ModelController


def to_snake_case(s: str) -> str:
    return "_".join(re.sub("([A-Z][a-z]+)", r" \1", re.sub("([A-Z]+)", r" \1", s.replace("-", " "))).split()).lower()


def add_model_method_name(cls: Type[ModelController], params: dict, *, plural: bool = False) -> None:
    if cls.__use_model_name__:
        name = cls.__model_name__ or to_snake_case(cls.__repository_cls__.__model__.__name__)
        params["name"] = f"{name}{plural and 's' or ''}"
