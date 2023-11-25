from typing import Annotated, Optional, Type

from api.utils import InMemoryDBRepository
from fastapi.params import Depends
from pydantic import Field
from pydantic.main import BaseModel, ModelMetaclass

from furiousapi.api import ModelController
from furiousapi.db import RepositoryConfig
from furiousapi.db.models import FuriousPydanticConfig


class Model(BaseModel):
    id: Optional[str] = Field(alias="_id")


class MyModel1(Model):
    my_param1: str

    class Config(FuriousPydanticConfig):
        pass


class MyModel2(Model):
    my_param2: str

    class Config(FuriousPydanticConfig):
        pass


class MyModel1Repository(InMemoryDBRepository[MyModel1]):  # type: ignore[type-arg]
    class Config(RepositoryConfig):
        @staticmethod
        def model_to_query(x: Type[MyModel1]) -> Type[MyModel1]:
            return x

        filter_model = ModelMetaclass


class MyModel2Repository(InMemoryDBRepository[MyModel2]):  # type: ignore[type-arg]
    class Config(RepositoryConfig):
        @staticmethod
        def model_to_query(x: Type[MyModel1]) -> Type[MyModel1]:
            return x

        filter_model = ModelMetaclass


def repository1_dependency() -> MyModel1Repository:
    return MyModel1Repository()


def repository2_dependency() -> MyModel2Repository:
    return MyModel2Repository()


class MyModel1Controller(ModelController):
    repository: Depends = Depends(repository1_dependency, use_cache=True)


class MyModel1Controller2(ModelController):
    repository: Annotated[MyModel1Repository, Depends] = Depends(repository1_dependency)  # type: ignore[assignment]
    __enabled_routes__ = ("get",)


class MyModel2Controller(ModelController):
    repository: Annotated[
        MyModel2Repository,
        Depends(repository2_dependency),
    ]
