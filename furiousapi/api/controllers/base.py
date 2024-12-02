from __future__ import annotations

import abc
import inspect
import logging
import sys
import typing
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
    Type,
    Union,
    _AnnotatedAlias,
    cast,
    get_args,
    get_type_hints,
    overload,
)

from fastapi import APIRouter, params
from fastapi.datastructures import Default
from fastapi.params import Depends
from fastapi.routing import APIRoute
from fastapi.utils import generate_unique_id
from starlette.responses import JSONResponse, Response

from furiousapi.core.exceptions import FuriousError
from furiousapi.db import BaseRepository  # noqa: TC001
from furiousapi.utils import NOT_SET
from furiousapi.utils._pydantic_compat import PYDANTIC_V2

from .utils import _add_self_as_dependency

if PYDANTIC_V2:
    from typing import ClassVar
else:
    from pydantic.typing import is_classvar

if TYPE_CHECKING:
    from enum import Enum

    from fastapi.routing import APIRoute
    from fastapi.types import IncEx
    from starlette.routing import BaseRoute

    if sys.version_info >= (3, 10):
        from typing import TypeAlias
    else:
        from typing_extensions import TypeAlias, Doc

from .mixins import (
    BaseRouteMixin,
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
Sentinel: TypeAlias = Depends

if sys.version_info >= (3, 11):
    from typing import NamedTuple

    class DependencyMetaData(NamedTuple):
        return_type: Any
        dependency: Depends

else:
    from collections import namedtuple

    DependencyMetaData: NamedTuple = namedtuple("DependencyMetaData", ("return_type", "dependency"))  # noqa: PYI024


def _is_dependency(member: str) -> bool:
    return isinstance(member, Depends)


def _is_annotated_dependency(dependency_hint: Any) -> bool:
    args = get_args(dependency_hint)
    return isinstance(dependency_hint, _AnnotatedAlias) and (args[1] is Depends or isinstance(args[1], Depends))


def _generate_init_fn_with_injected_dependencies(cls: type) -> None:
    old_init: Callable[..., Any] = cls.__init__  # type: ignore[misc]
    old_signature = inspect.signature(old_init)
    old_parameters: list[inspect.Parameter] = list(old_signature.parameters.values())[1:]  # drop `self` parameter
    new_parameters = [
        x for x in old_parameters if x.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]
    dependency_names: list[str] = []
    dependencies = _get_cls_dependencies(cls)

    for name, meta in dependencies.items():
        setattr(cls, f"__{name}_cls__", meta.return_type)
        if PYDANTIC_V2:
            pass
        elif is_classvar(cast(Type[Any], meta)):
            continue
        parameter_kwargs = {"default": meta.dependency}
        dependency_names.append(name)
        new_parameters.append(
            inspect.Parameter(
                name=name, kind=inspect.Parameter.KEYWORD_ONLY, annotation=meta.return_type, **parameter_kwargs
            ),
        )
    new_signature = old_signature.replace(parameters=new_parameters)

    def new_init(self: Any, *args, **kwargs) -> None:
        for dep_name in dependency_names:
            dep_value = kwargs.pop(dep_name, NOT_SET)
            if dep_value is NOT_SET:
                raise TypeError(f"__init__() missing required keyword argument: '{dep_name}'")
            setattr(self, dep_name, dep_value)

        old_init(self, *args, **kwargs)

    cls.__signature__ = new_signature  # type: ignore[misc,attr-defined]
    cls.__init__ = new_init  # type: ignore[misc]


def _get_cls_dependencies(cls: type) -> dict[str, DependencyMetaData]:
    dependencies_by_name = dict(inspect.getmembers(cls, _is_dependency))
    hints = get_type_hints(cls, include_extras=True)
    dependencies: dict[str, DependencyMetaData] = {}

    for dependency_name, dependency in dependencies_by_name.items():
        cls.__annotations__[dependency_name] = dependency
        real_dependency = dependency.dependency
        return_type = None
        if isinstance(real_dependency, type):  # is a class
            return_type = real_dependency
        elif callable(real_dependency):
            return_type = get_type_hints(real_dependency).get("return")
        else:
            logger.warning(
                f"dependency {dependency_name} has not defined return type hint __{dependency_name}__cls__ will be None"
            )
        dependencies[dependency_name] = DependencyMetaData(return_type, dependency)

    for dependency_name, dependency_hint in _get_annotated_dependencies(dependencies_by_name, hints):
        args = get_args(dependency_hint)
        return_type = args[0]
        dependencies[dependency_name] = DependencyMetaData(return_type, args[1])

    return dependencies


def _get_annotated_dependencies(dependencies_by_name: dict[str, Any], hints: dict) -> list[tuple[str, type]]:
    return [
        (name, hint)
        for name, hint in hints.items()
        if _is_annotated_dependency(hint) and name not in dependencies_by_name
    ]


def _is_route(member: str) -> bool:
    return inspect.isfunction(member) and getattr(member, IS_ROUTE, False)


@overload  # type: ignore[misc]
def action(
    path: Annotated[
        str,
        Doc(
            """
                The URL path to be used for this *path operation*.

                For example, in `http://example.com/items`, the path is `/items`.
                """
        ),
    ],
    *,
    response_model: Annotated[
        Any,
        Doc(
            """
                The type to use for the response.

                It could be any valid Pydantic *field* type. So, it doesn't have to
                be a Pydantic model, it could be other things, like a `list`, `dict`,
                etc.

                It will be used for:

                * Documentation: the generated OpenAPI (and the UI at `/docs`) will
                    show it as the response (JSON Schema).
                * Serialization: you could return an arbitrary object and the
                    `response_model` would be used to serialize that object into the
                    corresponding JSON.
                * Filtering: the JSON sent to the client will only contain the data
                    (fields) defined in the `response_model`. If you returned an object
                    that contains an attribute `password` but the `response_model` does
                    not include that field, the JSON sent to the client would not have
                    that `password`.
                * Validation: whatever you return will be serialized with the
                    `response_model`, converting any data as necessary to generate the
                    corresponding JSON. But if the data in the object returned is not
                    valid, that would mean a violation of the contract with the client,
                    so it's an error from the API developer. So, FastAPI will raise an
                    error and return a 500 error code (Internal Server Error).

                Read more about it in the
                [FastAPI docs for Response Model](https://fastapi.tiangolo.com/tutorial/response-model/).
                """
        ),
    ] = Default(None),
    status_code: Annotated[
        Optional[int],
        Doc(
            """
                The default status code to be used for the response.

                You could override the status code by returning a response directly.

                Read more about it in the
                [FastAPI docs for Response Status Code](https://fastapi.tiangolo.com/tutorial/response-status-code/).
                """
        ),
    ] = None,
    tags: Annotated[
        Optional[List[Union[str, Enum]]],
        Doc(
            """
                A list of tags to be applied to the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/#tags).
                """
        ),
    ] = None,
    dependencies: Annotated[
        Optional[Sequence[params.Depends]],
        Doc(
            """
                A list of dependencies (using `Depends()`) to be applied to the
                *path operation*.

                Read more about it in the
                [FastAPI docs for Dependencies in path operation decorators](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/).
                """
        ),
    ] = None,
    summary: Annotated[
        Optional[str],
        Doc(
            """
                A summary for the *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).
                """
        ),
    ] = None,
    description: Annotated[
        Optional[str],
        Doc(
            """
                A description for the *path operation*.

                If not provided, it will be extracted automatically from the docstring
                of the *path operation function*.

                It can contain Markdown.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).
                """
        ),
    ] = None,
    response_description: Annotated[
        str,
        Doc(
            """
                The description for the default response.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).
                """
        ),
    ] = "Successful Response",
    responses: Annotated[
        Optional[Dict[Union[int, str], Dict[str, Any]]],
        Doc(
            """
                Additional responses that could be returned by this *path operation*.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).
                """
        ),
    ] = None,
    deprecated: Annotated[
        Optional[bool],
        Doc(
            """
                Mark this *path operation* as deprecated.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).
                """
        ),
    ] = None,
    operation_id: Annotated[
        Optional[str],
        Doc(
            """
                Custom operation ID to be used by this *path operation*.

                By default, it is generated automatically.

                If you provide a custom operation ID, you need to make sure it is
                unique for the whole API.

                You can customize the
                operation ID generation with the parameter
                `generate_unique_id_function` in the `FastAPI` class.

                Read more about it in the
                [FastAPI docs about how to Generate Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).
                """
        ),
    ] = None,
    response_model_include: Annotated[
        Optional[IncEx],
        Doc(
            """
                Configuration passed to Pydantic to include only certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).
                """
        ),
    ] = None,
    response_model_exclude: Annotated[
        Optional[IncEx],
        Doc(
            """
                Configuration passed to Pydantic to exclude certain fields in the
                response data.

                Read more about it in the
                [FastAPI docs for Response Model - Return Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).
                """
        ),
    ] = None,
    response_model_by_alias: Annotated[
        bool,
        Doc(
            """
                Configuration passed to Pydantic to define if the response model
                should be serialized by alias when an alias is used.

                Read more about it in the
                [FastAPI docs for Response Model - Return Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_include-and-response_model_exclude).
                """
        ),
    ] = True,
    response_model_exclude_unset: Annotated[
        bool,
        Doc(
            """
                Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that were not set and
                have their default values. This is different from
                `response_model_exclude_defaults` in that if the fields are set,
                they will be included in the response, even if the value is the same
                as the default.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).
                """
        ),
    ] = False,
    response_model_exclude_defaults: Annotated[
        bool,
        Doc(
            """
                Configuration passed to Pydantic to define if the response data
                should have all the fields, including the ones that have the same value
                as the default. This is different from `response_model_exclude_unset`
                in that if the fields are set but contain the same default values,
                they will be excluded from the response.

                When `True`, default values are omitted from the response.

                Read more about it in the
                [FastAPI docs for Response Model - Return Type](https://fastapi.tiangolo.com/tutorial/response-model/#use-the-response_model_exclude_unset-parameter).
                """
        ),
    ] = False,
    response_model_exclude_none: Annotated[
        bool,
        Doc(
            """
                Configuration passed to Pydantic to define if the response data should
                exclude fields set to `None`.

                This is much simpler (less smart) than `response_model_exclude_unset`
                and `response_model_exclude_defaults`. You probably want to use one of
                those two instead of this one, as those allow returning `None` values
                when it makes sense.

                Read more about it in the
                [FastAPI docs for Response Model - Return Type](https://fastapi.tiangolo.com/tutorial/response-model/#response_model_exclude_none).
                """
        ),
    ] = False,
    include_in_schema: Annotated[
        bool,
        Doc(
            """
                Include this *path operation* in the generated OpenAPI schema.

                This affects the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Query Parameters and String Validations](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#exclude-from-openapi).
                """
        ),
    ] = True,
    response_class: Annotated[
        Type[Response],
        Doc(
            """
                Response class to be used for this *path operation*.

                This will not be used if you return a response directly.

                Read more about it in the
                [FastAPI docs for Custom Response - HTML, Stream, File, others](https://fastapi.tiangolo.com/advanced/custom-response/#redirectresponse).
                """
        ),
    ] = Default(JSONResponse),
    name: Annotated[
        Optional[str],
        Doc(
            """
                Name for this *path operation*. Only used internally.
                """
        ),
    ] = None,
    callbacks: Annotated[
        Optional[List[BaseRoute]],
        Doc(
            """
                List of *path operations* that will be used as OpenAPI callbacks.

                This is only for OpenAPI documentation, the callbacks won't be used
                directly.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for OpenAPI Callbacks](https://fastapi.tiangolo.com/advanced/openapi-callbacks/).
                """
        ),
    ] = None,
    openapi_extra: Annotated[
        Optional[Dict[str, Any]],
        Doc(
            """
                Extra metadata to be included in the OpenAPI schema for this *path
                operation*.

                Read more about it in the
                [FastAPI docs for Path Operation Advanced Configuration](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/#custom-openapi-path-operation-schema).
                """
        ),
    ] = None,
    generate_unique_id_function: Annotated[
        Callable[[APIRoute], str],
        Doc(
            """
                Customize the function used to generate unique IDs for the *path
                operations* shown in the generated OpenAPI.

                This is particularly useful when automatically generating clients or
                SDKs for your API.

                Read more about it in the
                [FastAPI docs about how to Generate Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).
                """
        ),
    ] = Default(generate_unique_id),
) -> Callable:
    pass


def action(path: str, **route_kwargs):
    def inner(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            if inspect.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return func(*args, **kwargs)

        setattr(wrapper, IS_ROUTE, True)
        setattr(wrapper, ROUTE_PATH, path)
        setattr(wrapper, ROUTE_KWARGS, route_kwargs)
        return wrapper

    return inner


class CBVMeta(abc.ABCMeta):
    def __new__(mcs, name: str, bases: tuple, namespace: dict, **router_kwargs) -> Any:
        cls: Type[CBV] = cast("Type[CBV]", super().__new__(mcs, name, bases, namespace))
        parents = [b for b in bases if isinstance(b, mcs)]
        if not parents or namespace.get("__abstract__", False):
            return cls

        _generate_init_fn_with_injected_dependencies(cls)

        if not hasattr(cls, "api_router") or not cls.api_router or not isinstance(cls.api_router, APIRouter):
            api_router = APIRouter(**router_kwargs)
            cls.api_router = api_router

        for _, route in inspect.getmembers(cls, _is_route):
            _add_self_as_dependency(cls, route)
            path = getattr(route, ROUTE_PATH)
            cls.api_router.add_api_route(path, route, **getattr(route, ROUTE_KWARGS))

        if issubclass(cls, BaseRouteMixin):
            cls.__bootstrap__()

        if cls.__enabled_routes__:
            cls.api_router.routes = [route for route in cls.api_router.routes if route.name in cls.__enabled_routes__]

        return cls


class CBV(abc.ABC, metaclass=CBVMeta):
    api_router: ClassVar[APIRouter]
    __enabled_routes__: ClassVar[Sequence[str]] = ()
    __route_config__: ClassVar[Dict[str, dict]] = {}
    __abstract__: bool = True


REPOSITORY = "repository"


class ModelController(
    CBV, GetModelMixin, ListModelMixin, CreateModelMixin, UpdateModelMixin, DeleteModelMixin
):  # type: ignore[misc]
    repository: Annotated[BaseRepository, Depends]
    __model_name__: str
    __use_model_name__: bool = False
    __abstract__ = True

    def __init__(self, *args, **kwargs): ...
    def __init_subclass__(cls, *args, **kwargs) -> None:
        if not issubclass(cls, ModelController):
            return

        repository_hint = typing.get_type_hints(cls, include_extras=True)[REPOSITORY]
        dependency_from_hint = None
        if typing.get_origin(repository_hint) is Annotated:
            dependency_from_hint = [x for x in repository_hint.__metadata__ if isinstance(x, Depends)]

        dependency_from_value = hasattr(cls, REPOSITORY) and isinstance(cls.repository, Depends)

        if not (dependency_from_value or dependency_from_hint):
            raise FuriousError(f"{REPOSITORY} must be a FastAPI Depends instance")
