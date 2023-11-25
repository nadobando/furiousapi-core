from typing import TYPE_CHECKING

from api.models import MyModel1, MyModel1Controller

from furiousapi.api import ModelController
from furiousapi.api.pagination import PaginatedResponse

if TYPE_CHECKING:
    from fastapi.routing import APIRoute


def test_create_signature(controller1: MyModel1Controller):
    create: APIRoute = get_route(controller1, "create")
    assert create.dependant.body_params[0].type_ == MyModel1
    assert create.response_model == MyModel1


def test_list_signature(controller1: MyModel1Controller):
    route: APIRoute = get_route(controller1, "list")
    pagination = route.dependant.dependencies[1]
    assert pagination.name == "pagination"
    for param, dep in zip(["limit", "pagination_type", "next"], pagination.query_params):
        assert param == dep.name

    filtering = route.dependant.query_params[2]
    assert filtering.name == "filtering"

    fields = route.dependant.query_params[0]
    assert fields.name == "fields"
    assert fields.type_ is controller1.repository.__fields__
    sorting = route.dependant.query_params[1]
    assert sorting.name == "sorting"
    assert sorting.type_ is controller1.repository.__sort__
    assert route.response_model == PaginatedResponse[MyModel1]


def test_get_signature(controller1: MyModel1Controller):
    get: APIRoute = get_route(controller1, "get")
    fields = get.dependant.query_params[0]
    assert get.response_model is MyModel1
    assert fields.type_ is controller1.repository.__fields__


def test_delete_signature(controller1: MyModel1Controller):
    delete: APIRoute = get_route(controller1, "delete")

    id_field = delete.dependant.path_params[0]
    assert id_field.alias == "id"
    assert id_field.required
    assert delete.response_model is None


def test_update_signature(controller1: MyModel1Controller):
    update: APIRoute = get_route(controller1, "update")
    assert update.response_model is MyModel1


def get_route(controller: ModelController, route: str) -> "APIRoute":
    return next(filter(lambda x: x.name == route, controller.api_router.routes))
