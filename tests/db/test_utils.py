from __future__ import annotations

from enum import Enum

import pytest
from pydantic import BaseModel

from furiousapi.db.utils import (  # get_model_sort_fields_enum,
    get_model_fields,
    get_model_fields_enum,
)


class InnerModel2(BaseModel):
    field: int


class InnerModel(BaseModel):
    inner2: InnerModel2


class MyModel(BaseModel):
    inner_model1: InnerModel
    flat: int


MyModelFieldsEnum = get_model_fields_enum(MyModel, recursive=True)


@pytest.mark.parametrize(
    ("recursive", "expected"),
    [
        (False, {"inner_model1": "inner_model1", "flat": "flat"}),
        (
            True,
            {
                "flat": "flat",
                "inner_model1": "inner_model1",
                "inner_model1.inner2": "inner_model1.inner2",
                "inner_model1.inner2.field": "inner_model1.inner2.field",
            },
        ),
    ],
)
def test_get_model_fields(recursive: bool, expected: dict):  # noqa: FBT001
    assert get_model_fields(MyModel, recursive=recursive) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [(None, f"{MyModel.__name__}FieldsEnum"), ("ChangedEnumName", "ChangedEnumName")],
)
def test_get_model_fields_enum(name: str, expected: tuple[str | None, str]):
    enum = get_model_fields_enum(MyModel, name)
    assert issubclass(enum, Enum)
    assert enum.__name__ == expected
