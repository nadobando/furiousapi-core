from typing import TYPE_CHECKING

from furiousapi.api import ModelController
from furiousapi.api.pagination import PaginatedResponse
from tests.api.models import MyModel1, MyModel1Controller
from tests.api.utils import get_most_inner_class

if TYPE_CHECKING:
    from fastapi.routing import APIRoute


def test_create_signature(controller1: MyModel1Controller):
    create: APIRoute = get_route(controller1, "create")
    assert create.dependant.body_params[0].type_ == MyModel1
    assert create.response_model == MyModel1


def test_list_signature(controller1: MyModel1Controller):
    route: APIRoute = get_route(controller1, "list")
    query_params = route.dependant.query_params
    assert query_params[0].name == "limit"
    assert query_params[1].name == "next_"
    assert query_params[2].name == "query"
    assert query_params[3].name == "pagination_type"
    assert route.response_model == PaginatedResponse[MyModel1]


def test_get_signature(controller1: MyModel1Controller):
    get: APIRoute = get_route(controller1, "get")
    fields = get.dependant.query_params[0]
    assert get.response_model is MyModel1
    assert get_most_inner_class(fields.type_) is controller1.get_fields


def test_delete_signature(controller1: MyModel1Controller):
    delete: APIRoute = get_route(controller1, "delete")
    id_field = delete.dependant.path_params[0]
    assert id_field.alias == "id"
    assert id_field.required
    assert delete.response_model in (None, type(None))


def test_replace_signature(controller1: MyModel1Controller):
    replace: APIRoute = get_route(controller1, "replace")
    assert replace.response_model is MyModel1


def test_patch_signature(controller1: MyModel1Controller):
    patch: APIRoute = get_route(controller1, "patch")
    assert patch.response_model is MyModel1


def get_route(controller: ModelController, route: str) -> "APIRoute":
    return next(filter(lambda x: x.name == route, controller.api_router.routes))
