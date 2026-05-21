from typing import Any, Dict, Literal, Optional, Type, Union, cast

from fastapi._compat import PYDANTIC_V2, FieldInfo, ModelField
from pydantic import BaseModel

# ``model_fields`` is ``Dict[str, FieldInfo]`` in pydantic v2;
# ``__fields__`` is ``Dict[str, ModelField]`` in pydantic v1. Expose both shapes
# under one alias so the conditional function variants have matching signatures.
FieldType = Union[FieldInfo, ModelField]

if PYDANTIC_V2:
    from pydantic import TypeAdapter
    from pydantic._internal._model_construction import ModelMetaclass

    def get_model_field(model: Type[BaseModel], attr: str) -> Optional[FieldType]:
        return model.model_fields.get(attr)

    def get_model_fields(model: Type[BaseModel]) -> Dict[str, FieldType]:
        return cast("Dict[str, FieldType]", model.model_fields)

    AllTypes = Optional[
        Literal[
            "none",
            "int",
            "bool",
            "float",
            "str",
            "bytes",
            "bytearray",
            "list",
            "tuple",
            "set",
            "frozenset",
            "generator",
            "dict",
            "datetime",
            "date",
            "time",
            "timedelta",
            "url",
            "multi-host-url",
            "json",
            "uuid",
            "any",
        ]
    ]

    def field_info_type(field_info: FieldType) -> Any:
        if not isinstance(field_info, FieldInfo):
            raise TypeError(f"Expected FieldInfo in pydantic v2 mode, got {type(field_info).__name__}")
        return TypeAdapter(field_info.annotation).core_schema.get("schema", {}).get("cls")

else:
    from pydantic.main import ModelMetaclass

    def get_model_fields(model: Type[BaseModel]) -> Dict[str, FieldType]:
        return cast("Dict[str, FieldType]", model.__fields__)

    def get_model_field(model: Type[BaseModel], attr: str) -> Optional[FieldType]:
        return get_model_fields(model).get(attr)

    def field_info_type(field_info: FieldType) -> Any:
        if not isinstance(field_info, ModelField):
            raise TypeError(f"Expected ModelField in pydantic v1 mode, got {type(field_info).__name__}")
        return field_info.type_


__all__ = [
    "PYDANTIC_V2",
    "FieldInfo",
    "FieldType",
    "ModelField",
    "ModelMetaclass",
    "field_info_type",
    "get_model_field",
    "get_model_fields",
]
