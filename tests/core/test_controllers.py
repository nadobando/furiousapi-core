import uuid
from enum import Enum
from http import HTTPStatus
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Type,
    Union,
)

import pytest
from fastapi import APIRouter, FastAPI, Query
from fastapi.params import Depends
from pydantic import BaseModel, Field
from pydantic.main import ModelMetaclass
from starlette.testclient import TestClient

from furiousapi.core.api.controllers import CBV, ModelController, action
from furiousapi.core.db.fields import SortableFieldEnum
from furiousapi.core.db.models import FuriousPydanticConfig
from furiousapi.core.db.repository import BaseRepository, RepositoryConfig
from furiousapi.core.pagination import AllPaginationStrategies, PaginatedResponse
from furiousapi.core.responses import BulkResponseModel
from furiousapi.core.types import TEntity, TModelFields

if TYPE_CHECKING:
    from fastapi.dependencies.models import Dependant
    from fastapi.routing import APIRoute


class MyCBV(CBV):
    @action("/endpoint1")
    def endpoint1(self, query_param: str = Query(...)):
        pass

    @action("/endpoint2")
    def endpoint2(self, query_param: str = Query(...)):
        pass


def test_cbv__when_no_api_router__then_initialize():
    assert isinstance(MyCBV.api_router, APIRouter)


static_api_router = APIRouter()


class MyCBV2(MyCBV):
    my_dep = Depends(lambda x: x)
    api_router = static_api_router


def test_cbv__when_api_router__then_use_it():
    assert id(MyCBV2.api_router) == id(static_api_router)


def test_cbv__actions_are_defined():
    my = MyCBV()
    assert len(MyCBV.api_router.routes) == 2  # noqa: PLR2004
    route1: APIRoute = my.api_router.routes[0]
    route2: APIRoute = my.api_router.routes[1]
    assert route1.path == "/endpoint1"
    assert route2.path == "/endpoint2"
    dependant: Dependant = route1.dependant

    assert dependant.query_params[0].type_ == str
    assert dependant.query_params[0].name == "query_param"
    assert dependant.query_params[0].required is True


def test_cbv__when_class_dependency_defined_and_not_passed__then_raise_type_error():
    with pytest.raises(TypeError):
        MyCBV2()


def test_cbv__when_class_dependency_defined__then_init_changed():
    try:
        MyCBV2(my_dep=Depends(repository_dependency))  # type: ignore[call-arg]
    except Exception:  # noqa: BLE001
        pytest.fail("something happened")


class MyModel(BaseModel):
    id: Optional[str] = Field(alias="_id")
    my_param: str

    class Config(FuriousPydanticConfig):
        pass


# TODO:
# mypy issue with Generic[TEntity]
class InMemoryDBRepository(BaseRepository[TEntity]):  # type: ignore[misc]
    def __init__(self) -> None:
        self._store: Dict[Union[str, int, Dict[str, Any], tuple], TEntity] = {}

    async def get(
        self,
        identifiers: Union[int, str, Dict[str, Any], tuple],
        fields: Optional[Iterable[Enum]] = None,  # noqa: ARG002
        *,
        should_error: bool = True,  # noqa: ARG002
    ) -> Optional[TEntity]:
        return self._store.get(identifiers)

    async def list(
        self,
        pagination: AllPaginationStrategies,  # noqa: ARG002
        fields: Optional[Iterable[TModelFields]] = None,  # noqa: ARG002
        sorting: Optional[List[SortableFieldEnum]] = None,  # noqa: ARG002
        filtering: Optional[TEntity] = None,  # noqa: ARG002
    ) -> PaginatedResponse[TEntity]:
        return PaginatedResponse[TEntity](total=len(self._store), items=list(self._store.values()), index=0, next=None)

    async def add(self, entity: TEntity) -> TEntity:

        if entity.id in self._store:  # type: ignore[attr-defined]
            raise ValueError(f"Key {entity.id} already exists")  # type: ignore[attr-defined]
        entity.id = str(uuid.uuid4())  # type: ignore[attr-defined]
        self._store[entity.id] = entity  # type: ignore[attr-defined]
        return entity

    async def update(self, entity: TEntity, **kwargs) -> Optional[TEntity]:
        if entity.id not in self._store:  # type: ignore[attr-defined]
            raise KeyError(f"Key {entity.id} does not exist")  # type: ignore[attr-defined]
        self._store[entity.id] = entity  # type: ignore[attr-defined]
        return entity

    async def delete(self, entity: Union[TEntity, str, int], **kwargs) -> None:

        if entity.id not in self._store:  # type: ignore[union-attr]
            raise KeyError(f"Key {entity.id} does not exist")  # type: ignore[union-attr]
        del self._store[entity.id]  # type: ignore[union-attr]

    async def bulk_create(self, bulk: List[TEntity]) -> BulkResponseModel:  # type: ignore[empty-body]
        pass

    async def bulk_delete(self, bulk: List[Union[TEntity, Any]]) -> List:  # type: ignore[empty-body]
        pass

    async def bulk_update(self, bulk: List[TEntity]) -> List:  # type: ignore[empty-body]
        pass


class MyRepository(InMemoryDBRepository[MyModel]):  # type: ignore[type-arg]
    class Config(RepositoryConfig):
        @staticmethod
        def model_to_query(x: Type[MyModel]) -> Type[MyModel]:
            return x

        filter_model = ModelMetaclass


repository = MyRepository()


def repository_dependency() -> MyRepository:
    return repository


class MyController(ModelController):
    repository: Depends = Depends(repository_dependency, use_cache=True)


class MyController2(ModelController):
    repository: Annotated[MyRepository, Depends] = Depends(repository_dependency)  # type: ignore[assignment]
    __enabled_routes__ = ("get",)


@pytest.fixture()
def controller() -> MyController:
    return MyController(repository=MyRepository())


def test_controller_repository__is_initialized(controller: MyController):
    assert isinstance(controller.repository, MyRepository)


def test_create(controller: MyController):
    create: APIRoute = next(filter(lambda x: x.name == "create", controller.api_router.routes))
    assert create.dependant.body_params[0].type_ == MyModel
    assert create.response_model == MyModel


def test_list(controller: MyController):
    route: APIRoute = next(filter(lambda x: x.name == "list", controller.api_router.routes))
    pagination = route.dependant.dependencies[1]
    assert pagination.name == "pagination"
    for param, dep in zip(["limit", "type", "next"], pagination.query_params):
        assert param == dep.name

    filtering = route.dependant.query_params[2]
    assert filtering.name == "filtering"

    fields = route.dependant.query_params[0]
    assert fields.name == "fields"
    assert fields.type_ is controller.repository.__fields__
    sorting = route.dependant.query_params[1]
    assert sorting.name == "sorting"
    assert sorting.type_ is controller.repository.__sort__
    assert route.response_model == PaginatedResponse[MyModel]


def test_get(controller: MyController):
    get: APIRoute = next(filter(lambda x: x.name == "get", controller.api_router.routes))
    fields = get.dependant.query_params[0]
    assert get.response_model is MyModel
    assert fields.type_ is controller.repository.__fields__


@pytest.mark.asyncio()
async def test_app():
    app = FastAPI()
    app.include_router(MyController.api_router)
    model = MyModel(my_param="1")

    client = TestClient(app)

    create_response = client.post("/", json=model.dict())
    assert create_response.status_code == HTTPStatus.OK
    doc = create_response.json()
    model.id = doc["_id"]
    get_response = client.get(f"/{doc['_id']}")
    assert get_response.status_code == HTTPStatus.OK
    assert get_response.json() == model.dict(by_alias=True)

    list_response = client.get("/")
    assert list_response.status_code == HTTPStatus.OK
    assert list_response.json()["items"][0] == model.dict(by_alias=True)


def test_api_router():
    assert id(MyController.api_router) != id(MyController2.api_router)


def test_model_controller__when__routes_defined__then_only_routes_defined():
    routes = MyController2.api_router.routes
    assert len(routes) == 1
    assert routes[0].name == "get"


def test_controller_no_overlapped_mixin():
    routes = [i.name for i in MyController.api_router.routes]
    duplicates = {x for x in routes if routes.count(x) > 1}
    assert not duplicates
