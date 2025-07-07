from typing import Any, Dict, Literal, Optional, Type, cast

from fastapi._compat import PYDANTIC_V2, FieldInfo, ModelField
from pydantic import BaseModel

if PYDANTIC_V2:
    from pydantic import TypeAdapter
    from pydantic._internal._model_construction import ModelMetaclass

    def get_model_field(model: Type[BaseModel], attr: str) -> FieldInfo:
        return model.model_fields.get(attr)

    def get_model_fields(model: Type[BaseModel]) -> Dict[str, FieldInfo]:
        return model.model_fields

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

    def field_info_type(field_info: FieldInfo) -> Any:
        return TypeAdapter(field_info.annotation).core_schema.get("schema", {}).get("cls")

else:
    from pydantic.main import ModelMetaclass
    from pydantic.v1.fields import FieldInfo

    def get_model_fields(model: Type[BaseModel]) -> Dict[str, FieldInfo]:
        return cast("Dict[str, FieldInfo]", model.__fields__)

    def get_model_field(model: Type[BaseModel], attr: str) -> FieldInfo:
        return get_model_fields(model).get(attr)

    def field_info_type(field_info: FieldInfo) -> Any:
        return field_info.type_


__all__ = [
    "PYDANTIC_V2",
    "FieldInfo",
    "ModelField",
    "ModelMetaclass",
    "field_info_type",
    "get_model_field",
    "get_model_fields",
]
