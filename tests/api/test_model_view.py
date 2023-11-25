from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from _pytest.fixtures import FixtureRequest
from api.models import (
    Model,
    MyModel1,
    MyModel1Controller,
    MyModel1Controller2,
    MyModel1Repository,
    MyModel2,
)

if TYPE_CHECKING:
    from starlette.testclient import TestClient


@pytest.mark.asyncio()
@pytest.mark.parametrize(
    ("path", "model", "repository"),
    [
        ("/model1", MyModel1(my_param1="1"), "repository1"),
        ("/model2", MyModel2(my_param2="1"), "repository2"),
    ],
)
async def test_create(
    test_client: "TestClient", path: str, model: "Model", request: FixtureRequest, repository: str
) -> None:
    repo = request.getfixturevalue(repository)
    await create_model(model, path, test_client)
    actual = await repo.get(model.id)
    assert actual == model


@pytest.mark.asyncio()
@pytest.mark.parametrize(
    ("path", "model"),
    [
        ("/model1", MyModel1(my_param1="1")),
        ("/model2", MyModel2(my_param2="1")),
    ],
)
async def test_get(test_client: "TestClient", path: str, model: "Model") -> None:
    await create_model(model, path, test_client)
    response = test_client.get(f"{path}/{model.id}")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == model.dict(by_alias=True)


@pytest.mark.asyncio()
@pytest.mark.parametrize(
    ("path", "model"),
    [
        ("/model1", MyModel1(my_param1="1")),
        ("/model2", MyModel2(my_param2="1")),
    ],
)
async def test_list(test_client: "TestClient", path: str, model: "Model") -> None:
    await create_model(model, path, test_client)

    list_response = test_client.get(path)
    assert list_response.status_code == HTTPStatus.OK
    assert list_response.json()["items"][0] == model.dict(by_alias=True)


@pytest.mark.asyncio()
@pytest.mark.parametrize(
    ("path", "model", "param"),
    [
        ("/model1", MyModel1(my_param1="1"), "my_param1"),
        ("/model2", MyModel2(my_param2="1"), "my_param2"),
    ],
)
async def test_update(test_client: "TestClient", path: str, model: "Model", param: str) -> None:
    await create_model(model, path, test_client)
    setattr(model, param, "new_value")
    response = test_client.put(path, json=model.dict())
    assert response.status_code == HTTPStatus.OK
    assert response.json() == model.dict(by_alias=True)


@pytest.mark.asyncio()
@pytest.mark.parametrize(
    ("path", "model"),
    [
        ("/model1", MyModel1(my_param1="1")),
        ("/model2", MyModel2(my_param2="1")),
    ],
)
async def test_delete(test_client: "TestClient", path: str, model: "Model") -> None:
    await create_model(model, path, test_client)

    response = test_client.delete(f"{path}/{model.id}")
    assert response.status_code == HTTPStatus.OK

    response = test_client.get(f"{path}/{model.id}")
    assert response.status_code == HTTPStatus.NOT_FOUND


async def create_model(model: "Model", path: str, test_client: "TestClient") -> None:
    create_response = test_client.post(path, json=model.dict())
    assert create_response.status_code == HTTPStatus.OK
    model.id = create_response.json()["_id"]


def test_api_router() -> None:
    assert id(MyModel1Controller.api_router) != id(MyModel1Controller2.api_router)


def test_model_controller__when__routes_defined__then_only_routes_defined() -> None:
    routes = MyModel1Controller2.api_router.routes
    assert len(routes) == 1
    assert routes[0].name == "get"


def test_controller_no_overlapped_mixin() -> None:
    routes = [i.name for i in MyModel1Controller.api_router.routes]
    duplicates = {x for x in routes if routes.count(x) > 1}
    assert not duplicates


def test_model_view__when_initialized__then_repository__is_initialized(controller1: MyModel1Controller) -> None:
    assert isinstance(controller1.repository, MyModel1Repository)
