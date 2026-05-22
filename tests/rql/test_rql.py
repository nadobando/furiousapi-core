import pytest
from pydantic import BaseModel

import tests.rql.text_queries
from furiousapi.rql.models import ModelRQL, TransformerConfig
from furiousapi.rql.transform import RQLModelTransform


@pytest.fixture
def rql_model(model: BaseModel) -> type[ModelRQL]:
    class MyModelRQL(ModelRQL):
        __model__ = model
        __transformer__ = RQLModelTransform

    return MyModelRQL


@pytest.fixture
def restricted_rql_model(model: BaseModel) -> type[ModelRQL]:
    class MyModelRQL(ModelRQL):
        __model__ = model
        __transformer__ = RQLModelTransform
        __transformer_params__ = TransformerConfig(
            allowed_fields={"id", "name", "children"},
            denied_fields={"forbidden_field"},
            allowed_sort={"id"},
            denied_sort={"forbidden_sort"},
            allowed_filters={"name": {"eq", "like"}, "id": {"eq"}},
            denied_filters={"name": {"ilike"}},
            wildcard_fields={"children.*": ["id", "name"]},
        )

    return MyModelRQL


@pytest.mark.parametrize(
    ("rql", "expected"), [pytest.param(*x["params"], id=x["id"]) for x in tests.rql.text_queries.ALL_TEST_CASES]
)
def test_rql_query(rql_model: ModelRQL, rql: str, expected: str) -> None:
    assert rql_model.parse(rql, "cursor") == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rql", "expected"), [pytest.param(*x["params"], id=x["id"]) for x in tests.rql.text_queries.ERROR_CASES]
)
def test_rql_query_error(restricted_rql_model: type[ModelRQL], rql: str, expected: type[Exception]) -> None:
    with pytest.raises(expected):
        restricted_rql_model.parse(rql, "cursor")
