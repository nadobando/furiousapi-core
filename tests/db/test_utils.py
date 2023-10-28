from enum import Enum
from typing import List, Optional, Tuple

import pytest
from pydantic import BaseModel

from furiousapi.core.db.fields import SortableFieldEnum
from furiousapi.core.db.utils import (
    create_subset_model,
    get_model_fields,
    get_model_fields_enum,
    get_model_sort_fields_enum,
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
def test_get_model_fields_enum(name: str, expected: Tuple[Optional[str], str]):
    enum = get_model_fields_enum(MyModel, name)
    assert issubclass(enum, Enum)
    assert enum.__name__ == expected


def test_get_model_sort_fields_enum():
    assert issubclass(get_model_sort_fields_enum(MyModel), SortableFieldEnum)


@pytest.mark.parametrize(
    ("projection", "expected"),
    [
        ({MyModelFieldsEnum.flat.value: 1}, ["flat"]),  # type: ignore[attr-defined]
        ({MyModelFieldsEnum.inner_model1.value: 1}, ["inner_model1"]),  # type: ignore[attr-defined]
        (
            {MyModelFieldsEnum.inner_model1.value: {MyModelFieldsEnum("inner_model1.inner2").value: 1}},  # type: ignore[attr-defined]
            ["inner_model1.inner2"],
        ),
        (
            {
                MyModelFieldsEnum.flat.value: 1,  # type: ignore[attr-defined]
                MyModelFieldsEnum.inner_model1.value: {MyModelFieldsEnum("inner_model1.inner2").value: 1},  # type: ignore[attr-defined]
            },  # type: ignore[attr-defined]
            ["inner_model1.inner2", "flat"],
        ),
    ],
)
def test_create_subset_model(projection: dict, expected: List[str]):
    actual = list(get_model_fields(create_subset_model(MyModel, projection), recursive=True).keys())
    for i in expected:
        assert i in actual
