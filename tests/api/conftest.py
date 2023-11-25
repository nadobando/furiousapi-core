import pytest
from api.models import (
    MyModel1Controller,
    MyModel1Repository,
    MyModel2Controller,
    MyModel2Repository,
    repository1_dependency,
    repository2_dependency,
)
from fastapi import FastAPI
from starlette.testclient import TestClient

from furiousapi.api.exception_handling import (
    furious_api_exception_handler,
    furious_db_exception_handler,
)
from furiousapi.api.exceptions import FuriousAPIError
from furiousapi.db.exceptions import FuriousEntityError


@pytest.fixture()
def repository1():
    return MyModel1Repository()


@pytest.fixture()
def repository2():
    return MyModel2Repository()


@pytest.fixture()
def controller1(repository1: MyModel1Repository) -> MyModel1Controller:
    return MyModel1Controller(repository=repository1)


@pytest.fixture()
def controller2(repository2: MyModel2Repository) -> MyModel1Controller:
    return MyModel2Controller(repository=repository2)


@pytest.fixture()
def app(
    repository1: MyModel1Repository,
    controller1: MyModel1Controller,
    repository2: MyModel2Repository,
    controller2: MyModel2Controller,
) -> FastAPI:
    app = FastAPI()
    app.include_router(controller1.api_router, prefix="/model1")
    app.include_router(controller2.api_router, prefix="/model2")

    app.add_exception_handler(FuriousEntityError, furious_db_exception_handler)
    app.add_exception_handler(FuriousAPIError, furious_api_exception_handler)

    app.dependency_overrides[repository1_dependency] = lambda: repository1
    app.dependency_overrides[repository2_dependency] = lambda: repository2

    return app


@pytest.fixture()
def test_client(app: FastAPI) -> TestClient:
    return TestClient(app)
