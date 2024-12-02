from __future__ import annotations

from typing import Annotated, Optional, Type

from fastapi.params import Depends
from pydantic import BaseModel, Field

from furiousapi.api import ModelController
from furiousapi.db import RepositoryConfig
from furiousapi.db.models import FuriousPydanticConfig
from furiousapi.utils._pydantic_compat import PYDANTIC_V2, ModelMetaclass
from tests.api.utils import InMemoryDBRepository


class Model(BaseModel):
    id: Optional[str] = Field(None, alias="_id")


class MyModel1(Model):
    my_param1: str
    if PYDANTIC_V2:
        model_config = FuriousPydanticConfig
    else:

        class Config(FuriousPydanticConfig):  # type: ignore[valid-type,misc]
            pass


class MyModel2(Model):
    my_param2: str

    if PYDANTIC_V2:
        model_config = FuriousPydanticConfig
    else:

        class Config(FuriousPydanticConfig):  # type: ignore[valid-type,misc]
            pass


class MyModel1Repository(InMemoryDBRepository[MyModel1]):  # type: ignore[type-arg]
    class Config(RepositoryConfig):
        @staticmethod
        def model_to_query(x: Type[MyModel1]) -> Type[MyModel1]:
            return x

        # TODO: fix this for pydantic v2
        filter_model = ModelMetaclass  # type: ignore[assignment]


class MyModel2Repository(InMemoryDBRepository[MyModel2]):  # type: ignore[type-arg]
    class Config(RepositoryConfig):
        @staticmethod
        def model_to_query(x: Type[MyModel1]) -> Type[MyModel1]:
            return x

        # TODO: fix this for pydantic v2
        filter_model = ModelMetaclass  # type: ignore[assignment]


def repository1_dependency() -> MyModel1Repository:
    return MyModel1Repository()


def repository2_dependency() -> MyModel2Repository:
    return MyModel2Repository()


class MyModel1Controller(ModelController):
    repository: Depends = Depends(repository1_dependency)


class MyModel1Controller2(ModelController):
    repository: Annotated[MyModel1Repository, Depends] = Depends(repository1_dependency)  # type: ignore[assignment]
    __enabled_routes__ = ("get",)


class MyModel2Controller(ModelController):
    repository: Annotated[
        MyModel2Repository,
        Depends(repository2_dependency),
    ]
