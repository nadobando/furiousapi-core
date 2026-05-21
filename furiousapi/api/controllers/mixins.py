from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from enum import Enum  # noqa: TC003
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Literal,
    Optional,
    Set,
    Type,
    Union,
    cast,
)

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, conlist

from furiousapi.api import error_responses
from furiousapi.api.controllers.utils import _prepare_endpoint, add_model_method_name
from furiousapi.api.pagination import PaginatedResponse, PaginationStrategyEnum
from furiousapi.api.responses import BulkResponseModel, PartialModelResponse
from furiousapi.core import config
from furiousapi.db import utils
from furiousapi.db.repository import BaseRepository  # noqa: TC001
from furiousapi.pydantic import PYDANTIC_V2

if TYPE_CHECKING:
    from furiousapi.api.controllers.base import (  # noqa: F401,RUF100
        ModelController,
        Sentinel,
    )
    from furiousapi.core.types import TEntity, TModelFields


class BaseRouteMixin(ABC):
    api_router: ClassVar[APIRouter]
    __route_config__: ClassVar[Dict[str, dict]]

    @classmethod
    def _get_route_params(cls, endpoint: str) -> dict:
        return cls.__route_config__.get(endpoint, {})

    # noinspection PyMethodParameters
    @classmethod
    @abstractmethod
    def __bootstrap__(cls, *args, **kwargs) -> None: ...


class RouteMixin(BaseRouteMixin, ABC):
    @staticmethod
    def _prepare_route(cls: Type[RouteMixin], endpoint: Callable[..., Any]) -> None:  # noqa: PLW0211
        route_params = cls._get_route_params(endpoint.__name__)
        api_router_method = getattr(cls.api_router, endpoint.__name__)
        endpoint = getattr(cls, endpoint.__name__)
        endpoint = _prepare_endpoint(cls, endpoint)
        api_router_method("/", **route_params)(endpoint)


class GetRouteMixin(RouteMixin):
    @classmethod
    def __bootstrap__(cls, *args, **kwargs) -> None:
        super().__bootstrap__(*args, **kwargs)
        cls._prepare_route(cls, cls.get)

    @abstractmethod
    def get(self, *args, **kwargs) -> Any:
        raise NotImplementedError


class PostRouteMixin(RouteMixin):
    @classmethod
    def __bootstrap__(cls, *args, **kwargs) -> None:
        super().__bootstrap__(*args, **kwargs)
        cls._prepare_route(cls, cls.post)

    @abstractmethod
    def post(self, *args, **kwargs) -> Any:
        raise NotImplementedError


class PutRouteMixin(RouteMixin, ABC):
    __method__ = "put"

    @classmethod
    def __bootstrap__(cls, *args, **kwargs) -> None:
        cls._prepare_route(cls, cls.put)
        super().__bootstrap__(*args, **kwargs)

    @abstractmethod
    def put(self, *args, **kwargs) -> Any:
        raise NotImplementedError


class PatchRouteMixin(RouteMixin):
    __method__ = "patch"

    @classmethod
    def __bootstrap__(cls, *args, **kwargs) -> None:
        cls._prepare_route(cls, cls.patch)
        super().__bootstrap__(*args, **kwargs)

    @abstractmethod
    def patch(self, *args, **kwargs) -> Any:
        raise NotImplementedError


class DeleteRouteMixin(RouteMixin):
    @classmethod
    def __bootstrap__(cls, *args, **kwargs) -> None:
        cls._prepare_route(cls, cls.delete)
        super().__bootstrap__(*args, **kwargs)

    @abstractmethod
    def delete(self, *args, **kwargs) -> Any:
        raise NotImplementedError


class OptionsRouteMixin(RouteMixin):
    @classmethod
    def __bootstrap__(cls, *args, **kwargs) -> None:
        cls._prepare_route(cls, cls.options)
        super().__bootstrap__(*args, **kwargs)

    @abstractmethod
    def options(self, *args, **kwargs) -> Any:
        raise NotImplementedError


class TraceRouteMixin(RouteMixin):
    @classmethod
    def __bootstrap__(cls, *args, **kwargs) -> None:
        cls._prepare_route(cls, cls.trace)
        super().__bootstrap__(*args, **kwargs)

    @abstractmethod
    def trace(self, *args, **kwargs) -> Any:
        raise NotImplementedError


class BaseModelRouteMixin(BaseRouteMixin, ABC):
    __endpoint__: str
    repository: BaseRepository
    __repository_cls__: ClassVar[Type[BaseRepository]]


class GetModelMixin(BaseModelRouteMixin):
    get_model: ClassVar[Optional[Type[BaseModel]]] = None
    get_fields: ClassVar[Optional[Type["Enum"]]] = None
    get_fields_recursive: ClassVar[bool] = False

    @classmethod
    def __bootstrap__(cls, **kwargs) -> None:
        super().__bootstrap__()
        _prepare_endpoint(cls, cls.get)

        signature = inspect.signature(cls.get)
        parameters = signature.parameters.copy()
        if not cls.get_fields:
            model = utils.get_model_fields_enum(cls.__repository_cls__.__model__, recursive=cls.get_fields_recursive)
            cls.get_fields = model

        if PYDANTIC_V2:
            list_anno1 = conlist(cls.get_fields, min_length=1)
        else:
            list_anno1 = conlist(cls.get_fields, min_items=1)  # type: ignore[call-arg]

        parameters["fields"] = parameters["fields"].replace(
            annotation=Optional[list_anno1],
        )
        signature_params: Dict[str, Any] = {"parameters": list(parameters.values())}
        if cls.get_model:
            signature_params["return_annotation"] = cls.get_model

        cls.get.__signature__ = signature.replace(**signature_params)  # type: ignore[attr-defined]
        responses = {404: {"model": error_responses.NotFoundHttpErrorDetails, "content": {"application/json": {}}}}
        params = {"responses": responses, "response_model": cls.get_model or cls.__repository_cls__.__model__}
        route_params = cls._get_route_params("get")
        params.update(route_params)
        add_model_method_name(cast("Type[ModelController]", cls), params)

        cls.api_router.get("/{id}", **params)(cls.get)

    async def get(
        self,
        id_: str = Path(..., alias="id"),
        fields: Optional[List[TModelFields]] = Query(None),
        # *args,
        # **kwargs,
    ) -> PartialModelResponse:
        result: Optional[BaseModel] = await self.repository.get(id_, fields)
        return PartialModelResponse(result)


class ListModelMixin(BaseModelRouteMixin):
    __filtering__: Optional[Any] = None
    __allowed_paginators__: ClassVar[Set[PaginationStrategyEnum]] = {
        PaginationStrategyEnum.CURSOR,
        PaginationStrategyEnum.OFFSET,
    }
    __include_in_schema_pagination_param__: ClassVar[bool] = True

    @classmethod
    def __bootstrap__(cls, *args, **kwargs) -> None:
        super().__bootstrap__(*args, **kwargs)
        _prepare_endpoint(cls, cls.list)

        signature = inspect.signature(cls.list)
        parameters = signature.parameters.copy()
        # TODO(rql): re-enable __filtering__ wiring once RQLStr-based pipeline is finalized.
        # if cls.__filtering__:
        #     parameters["query"] = parameters["query"].replace(annotation=cls.__filtering__, default=Query(None, alias="q"))  # noqa: ERA001, E501

        cls.list.__signature__ = signature.replace(parameters=list(parameters.values()))  # type: ignore[attr-defined]
        params = {"response_model": PaginatedResponse[cls.__repository_cls__.__model__]}  # type: ignore[name-defined]

        route_params = cls._get_route_params("list")
        params.update(route_params)

        add_model_method_name(cast("Type[ModelController]", cls), params, plural=True)
        cls.api_router.get("/", **params)(cls.list)

    async def list(
        self,
        limit: int = Query(
            config.pagination.default_size,
            le=config.pagination.max_size,
            description="limit the result set",
        ),
        next_: Union[int, str, None] = Query(None, alias="next"),
        query: str = Query(None, alias="q"),
        pagination_type: Literal[PaginationStrategyEnum.CURSOR, PaginationStrategyEnum.OFFSET] = Query(
            PaginationStrategyEnum.CURSOR, include_in_schema=__include_in_schema_pagination_param__
        ),
    ) -> PaginatedResponse:
        if query:
            if self.__filtering__:
                q = self.__filtering__.parse(query, pagination_type)
            else:
                q = query
        else:
            q = self.repository.query()
        paginator = self.repository.get_paginator(pagination_type)
        res = cast("PaginatedResponse", await paginator.get_page(q, limit, next_))

        return cast("PaginatedResponse", PartialModelResponse(res))


class CreateModelMixin(BaseModelRouteMixin):
    create_model: ClassVar[Optional[Type[BaseModel]]] = None

    @classmethod
    def __bootstrap__(cls, *args, **kwargs) -> None:
        super().__bootstrap__(*args, **kwargs)
        _prepare_endpoint(cls, cls.create)

        signature = inspect.signature(cls.create)
        responses = {409: {"model": error_responses.ConflictHttpErrorDetails, "content": {"application/json": {}}}}

        parameters = signature.parameters.copy()
        if (
            parameters["model"].annotation == "Union[BaseModel, TEntity]"
            or parameters["model"].annotation is inspect.Parameter.empty
        ):
            parameters["model"] = parameters["model"].replace(
                annotation=cls.create_model or cls.__repository_cls__.__model__,
            )

        cls.create.__signature__ = signature.replace(parameters=list(parameters.values()))  # type: ignore[attr-defined]
        params = {"responses": responses, "response_model": cls.__repository_cls__.__model__}
        route_params = cls._get_route_params("create")
        params.update(route_params)

        cls.api_router.post("/", **params)(cls.create)

    async def create(self, model: Union[BaseModel, TEntity]) -> TEntity:
        return await self.repository.add(model)


class UpdateModelMixin(BaseModelRouteMixin):
    update_model: ClassVar[Optional[Type[BaseModel]]] = None

    @classmethod
    def __bootstrap__(cls, *args, **kwargs) -> None:
        super().__bootstrap__(*args, **kwargs)
        _prepare_endpoint(cls, cls.update)

        signature = inspect.signature(cls.update)
        responses = {400: {"model": error_responses.BadRequestHttpErrorResponse, "content": {"application/json": {}}}}
        parameters = signature.parameters.copy()
        if (
            # not is_overriden or
            parameters["model"].annotation == "Union[BaseModel, TEntity]"
            or parameters["model"].annotation is inspect.Parameter.empty
        ):
            parameters["model"] = parameters["model"].replace(
                annotation=cls.update_model or cls.__repository_cls__.__model__,
            )

        cls.update.__signature__ = signature.replace(parameters=list(parameters.values()))  # type: ignore[attr-defined]
        params = {"responses": responses, "response_model": cls.__repository_cls__.__model__}
        route_params = cls._get_route_params("update")
        params.update(route_params)
        cls.api_router.put("/{id}", **params)(cls.update)

    async def update(self, model: Union[BaseModel, TEntity], id_: Any = Path(alias="id")) -> Any:
        return await self.repository.update(id_, model)


class DeleteModelMixin(BaseModelRouteMixin):
    @classmethod
    def __bootstrap__(cls, *args, **kwargs) -> None:
        super().__bootstrap__(*args, **kwargs)
        _prepare_endpoint(cls, cls.delete)

        responses = {404: {"model": error_responses.NotFoundHttpErrorDetails, "content": {"application/json": {}}}}
        params = {"responses": responses}
        route_params = cls._get_route_params("delete")
        params.update(route_params)

        cls.api_router.delete("/{id}", **params)(cls.delete)

    async def delete(self, id_: Union[str, int] = Path(..., alias="id")) -> None:
        return await self.repository.delete(id_)


class BulkBase(BaseModelRouteMixin, ABC):
    __bulk_route__ = "bulk"

    @staticmethod
    def set_route(cls, method, handler: Callable, **params) -> None:  # noqa: ANN001,PLW0211
        if method := getattr(cls.api_router, method):
            method(f"/{cls.__bulk_route__}", **params)(handler)
        else:
            raise AssertionError(f"{cls.__name__} should define {method}")


class BulkCreateModelMixin(BulkBase):
    create_model: Optional[Type[BaseModel]] = None
    bulk_response_model: ClassVar[Type[BaseModel]] = BulkResponseModel

    @classmethod
    def __bootstrap__(cls, *args, **kwargs) -> None:
        super().__bootstrap__(*args, **kwargs)
        _prepare_endpoint(cls, cls.bulk_create)

        responses = {409: {"model": error_responses.ConflictHttpErrorDetails, "content": {"application/json": {}}}}
        signature = inspect.signature(cls.bulk_create)
        parameters = signature.parameters.copy()
        if (
            parameters["bulk"].annotation == "List[Union[BaseModel, TEntity]]"
            or parameters["bulk"].annotation is inspect.Parameter.empty
        ):
            parameters["bulk"] = parameters["bulk"].replace(
                annotation=List[cls.create_model or cls.__repository_cls__.__model__],
            )

        cls.bulk_create.__signature__ = signature.replace(  # type: ignore[attr-defined]
            parameters=list(parameters.values())
        )
        params = {"responses": responses, "response_model": List[cls.bulk_response_model]}  # type: ignore[name-defined]
        route_params = cls._get_route_params("bulk_create")
        params.update(route_params)

        cls.set_route(cls, "post", cls.bulk_create, **params)

    async def bulk_create(self, bulk: List[Union[BaseModel, TEntity]]) -> BulkResponseModel:
        return await self.repository.bulk_create(bulk)


class BulkUpdateModelMixin(BulkBase):
    update_model: ClassVar[Optional[Type[BaseModel]]] = None

    @classmethod
    def __bootstrap__(cls, *args, **kwargs) -> Any:
        super().__bootstrap__(*args, **kwargs)
        _prepare_endpoint(cls, cls.bulk_update)

        responses = {409: {"model": error_responses.ConflictHttpErrorDetails, "content": {"application/json": {}}}}
        signature = inspect.signature(cls.bulk_update)
        parameters = signature.parameters.copy()
        if (
            # not is_overriden or
            parameters["bulk"].annotation == "List[Union[BaseModel, TEntity]]"
            or parameters["bulk"].annotation is inspect.Parameter.empty
        ):
            parameters["bulk"] = parameters["bulk"].replace(
                annotation=List[cls.update_model or cls.__repository_cls__.__model__],
            )

        cls.bulk_update.__signature__ = signature.replace(  # type: ignore[attr-defined]
            parameters=list(parameters.values()),
        )
        params = {
            "responses": responses,
            "response_model": List[cls.__repository_cls__.__model__],  # type: ignore[name-defined]
        }
        route_params = cls._get_route_params("bulk_update")
        params.update(route_params)

        cls.set_route(cls, "put", cls.bulk_update, **params)

    async def bulk_update(self, bulk: list[Any]) -> Any:
        return await self.repository.bulk_update(bulk)


class BulkDeleteModelMixin(BulkBase):
    __method__: ClassVar[str] = "bulk_delete"

    @classmethod
    def __bootstrap__(cls, *args, **kwargs) -> None:
        super().__bootstrap__(*args, **kwargs)
        _prepare_endpoint(cls, cls.bulk_delete)

        responses = {409: {"model": error_responses.ConflictHttpErrorDetails, "content": {"application/json": {}}}}
        signature = inspect.signature(cls.bulk_delete)
        parameters = signature.parameters.copy()
        annotation = cls.__repository_cls__.__model__.__fields__["id"].annotation
        if (
            parameters["bulk"].annotation == "List[Union[BaseModel, TEntity]]"
            or parameters["bulk"].annotation is inspect.Parameter.empty
        ):
            parameters["bulk"] = parameters["bulk"].replace(
                annotation=List[annotation],  # type: ignore[valid-type]
            )

        cls.bulk_delete.__signature__ = signature.replace(  # type: ignore[attr-defined]
            parameters=list(parameters.values())
        )
        params = {
            "responses": responses,
            "response_model": List[annotation],  # type: ignore[valid-type]
        }
        route_params = cls._get_route_params("bulk_delete")
        params.update(route_params)

        cls.set_route(cls, "delete", cls.bulk_delete, **params)

    async def bulk_delete(self, bulk: List[Any]) -> Any:
        return await self.repository.bulk_delete(bulk)
