import inspect
import re
import types
from typing import TYPE_CHECKING, Any, Callable, List, Type

from fastapi.params import Depends

if TYPE_CHECKING:
    from furiousapi.api.controllers import ModelController
    from furiousapi.api.controllers.mixins import BaseRouteMixin


def to_snake_case(s: str) -> str:
    return "_".join(re.sub("([A-Z][a-z]+)", r" \1", re.sub("([A-Z]+)", r" \1", s.replace("-", " "))).split()).lower()


def add_model_method_name(cls: "Type[ModelController]", params: dict, *, plural: bool = False) -> None:
    if cls.__use_model_name__:
        name = cls.__model_name__ or to_snake_case(cls.__repository_cls__.__model__.__name__)
        params["name"] = f"{name}{plural and 's' or ''}"


def _prepare_endpoint(cls: "Type[BaseRouteMixin]", endpoint: Callable[..., Any]) -> Callable[..., Any]:
    endpoint = duplicate_function(endpoint)
    _add_self_as_dependency(cls, endpoint)
    setattr(cls, endpoint.__name__, endpoint)
    return endpoint


def _add_self_as_dependency(cls: Type[Any], route: Callable[..., Any]) -> None:
    """
    Fixes the endpoint signature for a cbv route to ensure FastAPI performs dependency injection properly.
    """

    old_signature = inspect.signature(route)
    old_parameters: List[inspect.Parameter] = list(old_signature.parameters.values())
    old_first_parameter = old_parameters[0]
    new_first_parameter = old_first_parameter.replace(default=Depends(cls))
    new_parameters = [new_first_parameter] + [
        parameter.replace(kind=inspect.Parameter.KEYWORD_ONLY) for parameter in old_parameters[1:]
    ]
    new_signature = old_signature.replace(parameters=new_parameters)
    route.__signature__ = new_signature  # type:ignore[attr-defined]


def duplicate_function(original_function: Callable) -> Callable:
    """
    Duplicates a given function.

    :param original_function: The function to duplicate.
    :return: A new function with the same behavior as the original.
    """
    return types.FunctionType(
        original_function.__code__,
        original_function.__globals__,
        name=original_function.__name__,
        argdefs=original_function.__defaults__,
        closure=original_function.__closure__,
    )
