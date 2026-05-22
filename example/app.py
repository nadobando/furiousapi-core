from typing import Any, ClassVar, Generic

import uvicorn
from fastapi import FastAPI, Query
from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic_core import core_schema

from furiousapi.core.types import TEntity
from furiousapi.rql.models import ModelRQL
from furiousapi.rql.transform import RQLModelTransform


class DummyEntity(BaseModel):
    a: str


class MyModelRQL(ModelRQL[DummyEntity]):
    __model__: type[TEntity] = DummyEntity
    __transformer__ = RQLModelTransform


class RQLStr(str, Generic[TEntity]):
    __model__: type[ModelRQL] = MyModelRQL
    __pagination__: ClassVar[str] = "cursor"  # Default

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        def validate_rql(value: str) -> str:
            try:
                value = cls.__model__().parse(value, cls.__pagination__)

                return value
            except Exception as e:
                raise ValueError(f"Invalid RQL query: {e}")

        return core_schema.no_info_after_validator_function(
            validate_rql,
            core_schema.str_schema(),
        )


# Concrete implementation
class MyRQLStr(RQLStr[DummyEntity]):
    __model__ = DummyEntity


# Pydantic request model
class QueryParams(BaseModel):
    q: MyRQLStr


# FastAPI app
app = FastAPI()


@app.get("/search")
def search(params: QueryParams = Query(...)):
    return {"query": params.q}


if __name__ == "__main__":
    uvicorn.run(app, port=8084)
