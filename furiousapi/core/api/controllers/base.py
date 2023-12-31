from __future__ import annotations

import abc
import inspect
import logging
from functools import wraps

# noinspection PyUnresolvedReferences
from typing import (  # type:ignore[attr-defined]
    TYPE_CHECKING,
    Annotated,
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
    _AnnotatedAlias,
    cast,
    get_args,
    get_type_hints,
    overload,
)

from fastapi import APIRouter
from fastapi.datastructures import Default, DefaultPlaceholder
from fastapi.params import Depends
from fastapi.utils import generate_unique_id
from pydantic.typing import is_classvar
from starlette.responses import JSONResponse, Response

from furiousapi.core.exceptions import FuriousError
from furiousapi.utils import NOT_SET

if TYPE_CHECKING:
    from enum import Enum
    from types import GenericAlias

    from fastapi.encoders import DictIntStrAny, SetIntStr
    from fastapi.routing import APIRoute
    from starlette.routing import BaseRoute

    try:
        from typing import TypeAlias  # type: ignore[attr-defined]
    except ImportError:
        from typing_extensions import TypeAlias

from .mixins import (
    BaseRouteMixin,
    BulkCreateModelMixin,
    BulkDeleteModelMixin,
    BulkUpdateModelMixin,
    CreateModelMixin,
    DeleteModelMixin,
    GetModelMixin,
    ListModelMixin,
    UpdateModelMixin,
)

logger = logging.getLogger(__name__)

IS_ROUTE = "__furious_route__"
ROUTE_PATH = "__furious_route_path__"
ROUTE_KWARGS = "__furious_route_kwargs__"
NoneType = type(None)
Sentinel: TypeAlias = Annotated[NoneType, Depends]


def _type_is_sentinel(type_: GenericAlias) -> bool:
    """
    Check if the given type is a Sentinel.

    :param type_: A `GenericAlias` instance representing a type annotation.
    :type type_: `GenericAlias`

    :return: A boolean indicating whether the given type is a Sentinel.
    :rtype: `bool`
    """
    return type_ is Sentinel


def _class_has_sentinels(cls: Type[Any]) -> bool:
    """
    Check if the given class has any attributes with Sentinel types.

    :param cls: The class to inspect.
    :type cls: type

    :return: True if the class has any attributes with Sentinel types, False otherwise.
    :rtype: bool
    """
    class_sentinels = [
        name for name, hint in get_type_hints(cls, include_extras=True).items() if _type_is_sentinel(hint)
    ]

    dependencies_values = dict(inspect.getmembers(cls, _is_dependency))
    for name in class_sentinels:
        if name not in dependencies_values:
            return True
        if isinstance(dependencies_values[name], Depends):
            class_sentinels.remove(name)

    return bool(class_sentinels)


def _update_cbv_route_endpoint_signature(cls: Type[Any], route: Callable[..., Any]) -> None:
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


def _is_dependency(member: str) -> bool:
    return isinstance(member, Depends)


def _is_annotated_dependency(dependency_hint: Any) -> bool:
    args = get_args(dependency_hint)
    return isinstance(dependency_hint, _AnnotatedAlias) and args[1] is Depends


def _is_mixin(cls: Type) -> bool:
    return (
        issubclass(cls, BaseRouteMixin)
        and cls is not BaseRouteMixin
        and not isinstance(cls, CBVMeta)
        and not inspect.isabstract(cls)
    )


def _new_init(cls: Type) -> None:
    old_init: Callable[..., Any] = cls.__init__
    old_signature = inspect.signature(old_init)
    old_parameters: list[inspect.Parameter] = list(old_signature.parameters.values())[1:]  # drop `self` parameter
    new_parameters = [
        x for x in old_parameters if x.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]
    dependency_names: List[str] = []

    dependencies = _get_cls_dependencies_values(cls)

    for name, hint in dependencies:
        setattr(cls, f"__{name}_cls__", hint)
        if is_classvar(cast(Type[Any], hint)):
            continue
        parameter_kwargs = {"default": getattr(cls, name, Ellipsis)}
        dependency_names.append(name)
        new_parameters.append(
            inspect.Parameter(name=name, kind=inspect.Parameter.KEYWORD_ONLY, annotation=hint, **parameter_kwargs),
        )
    new_signature = old_signature.replace(parameters=new_parameters)

    def new_init(self: Any, *args, **kwargs) -> None:
        for dep_name in dependency_names:
            dep_value = kwargs.pop(dep_name, NOT_SET)
            if dep_value is NOT_SET:
                raise TypeError(f"__init__() missing required keyword argument: '{dep_name}'")
            setattr(self, dep_name, dep_value)

        old_init(self, *args, **kwargs)

    cls.__signature__ = new_signature
    cls.__init__ = new_init


def _get_cls_dependencies_values(cls: Type) -> Set[Tuple[str, Type]]:
    dependencies: Set[Tuple[str, Type]] = set()
    dependencies_by_name = dict(inspect.getmembers(cls, _is_dependency))
    hints = get_type_hints(cls, include_extras=True)

    for dependency_name, dependency in dependencies_by_name.items():
        cls.__annotations__[dependency_name] = dependency
        return_type = get_type_hints(dependency.dependency).get("return")
        logger.warning(
            f"dependency {dependency_name} has not defined return type hint __{dependency_name}__cls__ will be None"
        )
        dependencies.add((dependency_name, cast(Type, return_type)))

    for dependency_name, dependency_hint in _get_annotated_dependencies(dependencies_by_name, hints):
        args = get_args(dependency_hint)
        return_type = args[0]
        dependencies.add((dependency_name, cast(Type, return_type)))

    return dependencies


def _get_annotated_dependencies(dependencies_by_name: dict[str, Any], hints: dict) -> List[Tuple[str, Type]]:
    return [
        (name, hint)
        for name, hint in hints.items()
        if _is_annotated_dependency(hint) and name not in dependencies_by_name
    ]


def _is_route(member: str) -> bool:
    return inspect.isfunction(member) and getattr(member, IS_ROUTE, False)


@overload  # type: ignore[misc]
def action(
    path: str,
    *,
    response_model: Optional[Type[Any]] = None,
    status_code: Optional[int] = None,
    tags: Optional[List[Union[str, Enum]]] = None,
    dependencies: Optional[Sequence[Depends]] = None,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    response_description: str = "Successful Response",
    responses: Optional[Dict[Union[int, str], Dict[str, Any]]] = None,
    deprecated: Optional[bool] = None,
    methods: Optional[Union[Set[str], List[str]]] = None,
    operation_id: Optional[str] = None,
    response_model_include: Optional[Union[SetIntStr, DictIntStrAny]] = None,
    response_model_exclude: Optional[Union[SetIntStr, DictIntStrAny]] = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    response_model_exclude_none: bool = False,
    include_in_schema: bool = True,
    response_class: Union[Type[Response], DefaultPlaceholder] = Default(JSONResponse),
    name: Optional[str] = None,
    route_class_override: Optional[Type[APIRoute]] = None,
    callbacks: Optional[List[BaseRoute]] = None,
    openapi_extra: Optional[Dict[str, Any]] = None,
    generate_unique_id_function: Union[Callable[[APIRoute], str], DefaultPlaceholder] = Default(
        generate_unique_id,
    ),
) -> Callable:
    pass


def action(path: str, **route_kwargs):
    def inner(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            return await func(*args, **kwargs)

        setattr(wrapper, IS_ROUTE, True)
        setattr(wrapper, ROUTE_PATH, path)
        setattr(wrapper, ROUTE_KWARGS, route_kwargs)
        return wrapper

    return inner


class CBVMeta(abc.ABCMeta):
    __enabled_routes__: Union[Set[str], List[str], Tuple[str]]
    api_router: APIRouter

    def __new__(mcs, name: str, bases: tuple, namespace: dict, **router_kwargs) -> Any:
        cls = super().__new__(mcs, name, bases, namespace)
        parents = [b for b in bases if isinstance(b, mcs)]
        if not parents:
            return cls
        if _class_has_sentinels(cls):
            return cls

        _new_init(cls)

        if not hasattr(cls, "api_router") or not cls.api_router or not isinstance(cls.api_router, APIRouter):
            api_router = APIRouter(**router_kwargs)
            cls.api_router = api_router

        for _, route in inspect.getmembers(cls, _is_route):
            _update_cbv_route_endpoint_signature(cls, route)
            cls.api_router.add_api_route(getattr(route, ROUTE_PATH), route, **getattr(route, ROUTE_KWARGS))

        mixins: list[Type[BaseRouteMixin]] = cast(
            list[Type[BaseRouteMixin]], [b for b in cls.mro()[1:] if _is_mixin(b)]
        )

        for mix in mixins:
            try:
                endpoint: Callable[..., Optional[Any]] = getattr(mix, cast(str, mix.__method_name__))
            except AttributeError as e:
                raise FuriousError(f"endpoint {mix.__method_name__} must be defined") from e

            _update_cbv_route_endpoint_signature(cls, endpoint)
            mix.__bootstrap__(cls)

        if cls.__enabled_routes__:
            cls.api_router.routes = [
                route
                for route in cls.api_router.routes
                if route.name in cls.__enabled_routes__  # type: ignore[attr-defined]
            ]

        return cls


class CBV(abc.ABC, metaclass=CBVMeta):
    api_router: ClassVar[APIRouter]
    __enabled_routes__: ClassVar[Sequence[str]] = ()


class ModelController(
    CBV, GetModelMixin, ListModelMixin, CreateModelMixin, UpdateModelMixin, DeleteModelMixin
):  # type: ignore[misc]
    repository: Sentinel  # type: ignore[assignment]
    __model_name__: str
    __use_model_name__: bool = False

    @classmethod
    def __new__(cls, *args, **kwargs):  # noqa: ANN206
        if not isinstance(cls.repository, Depends):
            raise FuriousError("repository must be a FastAPI Depends instance")
        return super().__new__(cls)


class BulkView(BulkCreateModelMixin, BulkUpdateModelMixin, BulkDeleteModelMixin, ModelController): ...
