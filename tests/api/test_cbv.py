from http import HTTPStatus
from typing import TYPE_CHECKING, ClassVar

import pytest
import rich
from api.models import repository1_dependency
from fastapi import APIRouter, FastAPI, Query
from fastapi.params import Depends
from starlette.testclient import TestClient

from furiousapi.api import CBV, action
from furiousapi.api.controllers.mixins import GetRouteMixin, PostRouteMixin
from furiousapi.api.error_responses import NotFoundHttpErrorDetails

if TYPE_CHECKING:
    from fastapi.dependencies.models import Dependant
    from fastapi.routing import APIRoute

GET_RESPONSES = {404: {"model": NotFoundHttpErrorDetails}}


class MyCBV(CBV, GetRouteMixin, PostRouteMixin):
    __route_config__: ClassVar = {"get": {"responses": GET_RESPONSES}}

    @action("/endpoint1")
    async def endpoint1(self, q: str = Query(...)):
        pass

    @action("/endpoint2")
    async def endpoint2(self, q: str = Query(...)):
        pass

    def get(self, q1: str) -> None:
        pass

    def post(self, q2: str) -> None:
        pass


def test_cbv__when_no_api_router__then_initialize():
    assert isinstance(MyCBV.api_router, APIRouter)


static_api_router = APIRouter()


class MyCBV2(CBV):
    my_dep = Depends(lambda x: x)
    api_router = static_api_router

    @action("/endpoint1")
    def endpoint1(self, query_param: str = Query(...)):
        pass

    @action("/endpoint2")
    def endpoint2(self, query_param: str = Query(...)):
        pass


def test_cbv__when_api_router__then_use_it():
    assert id(MyCBV2.api_router) == id(static_api_router)


def test_cbv__actions_are_defined():
    my = MyCBV()
    assert len(MyCBV.api_router.routes) == 4  # noqa: PLR2004
    route1: APIRoute = my.api_router.routes[0]
    route2: APIRoute = my.api_router.routes[1]
    assert route1.path == "/endpoint1"
    assert route2.path == "/endpoint2"
    dependant: Dependant = route1.dependant

    assert dependant.query_params[0].type_ == str
    assert dependant.query_params[0].name == "q"
    assert dependant.query_params[0].required is True


def test_cbv__when_class_dependency_defined_and_not_passed__then_raise_type_error():
    with pytest.raises(TypeError):
        MyCBV2()


def test_cbv__when_class_dependency_defined__then_init_changed():
    try:
        rich.print(MyCBV2.api_router.routes)
        MyCBV2(my_dep=Depends(repository1_dependency))  # type: ignore[call-arg]
    except Exception:  # noqa: BLE001
        pytest.fail("something happened")


def test_cbv__when_using_mixin__then_mixin_is_configurable():
    cbv = MyCBV()  # type: ignore[call-arg]
    route = next(filter(lambda x: x.name == "get", cbv.api_router.routes))
    assert route
    assert route.responses == GET_RESPONSES


def test_cbv_in_app():
    app = FastAPI()
    app.include_router(MyCBV.api_router)

    client = TestClient(app)

    assert client.post("/?q2=a").status_code == HTTPStatus.OK
    assert client.get("/?q1=a").status_code == HTTPStatus.OK
    assert client.get("/endpoint1?q=a").status_code == HTTPStatus.OK
    assert client.get("/endpoint2?q=a").status_code == HTTPStatus.OK
