from __future__ import annotations

import inspect
import logging
import sys
from enum import Enum
from functools import lru_cache
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
)

import fastapi._compat
from fastapi import Query
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from furiousapi.db.consts import ANNOTATIONS
from furiousapi.pydantic import PYDANTIC_V2

if sys.version_info >= (3, 11):
    from typing import NamedTuple
else:
    from typing_extensions import NamedTuple
if PYDANTIC_V2:
    from pydantic import ConfigDict

    if sys.version_info >= (3, 11):
        from typing import TypeAlias

        ConfigType: TypeAlias = ConfigDict
    else:
        ConfigType = ConfigDict
else:
    from pydantic import BaseConfig, Extra

    if sys.version_info >= (3, 11):

        ConfigType: TypeAlias = Type[BaseConfig]  # type: ignore[misc]
    else:
        ConfigType = Type[BaseConfig]  # type: ignore[misc]
if TYPE_CHECKING:
    from furiousapi.pydantic import ModelField

logger = logging.getLogger(__name__)


class NotSet:
    def __repr__(self) -> str:
        return "<NOT_SET>"


NOT_SET = NotSet()


def get_model_fields(
    model: Type[BaseModel], include: Optional[Set[str]] = None, *, recursive: bool = False
) -> Dict[str, str]:
    keys = {}
    if PYDANTIC_V2:
        config = model.model_config
    else:
        config = model.Config  # type: ignore[attr-defined]
    alias_generator = getattr(config, "alias_generator", lambda x: x) or (lambda x: x)
    if PYDANTIC_V2:
        model_fields = {x.name: x for x in fastapi._compat.get_model_fields(model)}  # noqa: SLF001
    else:
        model_fields = model.__fields__  # type: ignore[assignment]
    for key, value in model_fields.items():
        if recursive and isinstance(value.type_, type) and issubclass(value.type_, BaseModel):
            keys.update({key: alias_generator(key)})
            sub_fields = get_model_fields(value.type_, include, recursive=recursive)
            for child_key, child_value in sub_fields.items():
                keys.update({f"{key}.{child_key}": f"{key}.{alias_generator(child_value)}"})
        else:
            keys.update({key: alias_generator(key)})

    if include:
        return {k: v for k, v in keys.items() if k in include}

    return keys


def get_model_fields_enum(
    model: Type[BaseModel],
    override_name: Optional[str] = None,
    *,
    include: Optional[Set[str]] = None,
    exclude: Optional[Set[str]] = None,
    recursive: bool = False,
) -> Type[Enum]:
    fields = get_model_fields(model, include, recursive=recursive)
    if exclude:
        fields = {k: v for k, v in fields.items() if k not in exclude}

    name = override_name or f"{model.__name__}FieldsEnum"
    return Enum(name, fields)  # type: ignore[return-value]


class FieldAlias(NamedTuple):
    name: str
    field: "ModelField"


@lru_cache
def model_alias_mapping(model: Type[BaseModel]) -> Dict[Optional[str], FieldAlias]:
    aliases = {}
    if PYDANTIC_V2:
        model_fields: dict = model.model_fields
    else:
        model_fields: dict = model.__fields__  # type: ignore[assignment]

    for k, v in model_fields.items():
        aliases[v.alias] = FieldAlias(k, v)

    return aliases


Projection = Dict[str, Union[int, Dict[str, Any]]]


def build_config() -> ConfigType:
    if PYDANTIC_V2:
        return ConfigDict(extra="ignore")
    config = BaseConfig
    config.extra = Extra.ignore  # type: ignore[attr-defined]
    return config  # type: ignore[return-value]


def clean_dict(d: dict) -> dict:
    stack: List[Iterator[Tuple[str, Any]]] = [iter(d.items())]
    dict_ = {}

    while stack:
        _next: Union[NotSet, Tuple[str, Any]] = next(stack[-1], NOT_SET)
        if isinstance(_next, NotSet):
            stack.pop()
        else:
            k, v = _next
            if isinstance(v, dict):
                stack.append(iter(v.items()))
            elif v is not None:
                dict_[k] = v

    return dict_


def _convert_pydantic(_: str, namespaces: dict, __: tuple) -> None:
    annotations: Dict[str, Any] = namespaces.get(ANNOTATIONS, {})
    for field in annotations:
        annotations[field] = Optional[annotations[field]]
        field_info: Optional[FieldInfo] = namespaces.get(field)
        if field_info and isinstance(field_info, FieldInfo) and field_info.default is Ellipsis:
            field_info.default = None

    namespaces[ANNOTATIONS] = annotations


def _remove_extra_data_from_signature(cls: Type[BaseModel]) -> None:
    sig = inspect.signature(cls)
    parameters = dict(sig.parameters)
    parameters.pop("extra_data", None)
    cls.__signature__ = sig.replace(parameters=list(parameters.values()))


def init_query_param(
    model_field: "ModelField", name: str, alias: str, parameter: inspect.Parameter
) -> inspect.Parameter:
    annotation = model_field.annotation
    if PYDANTIC_V2:
        field_info = model_field
        if isinstance(model_field.json_schema_extra, dict):
            extra = model_field.json_schema_extra
        else:
            extra = {}
    else:
        extra = model_field.field_info.extra
        field_info = model_field.field_info

    return inspect.Parameter(
        name=name,
        kind=parameter.kind,
        annotation=annotation,
        default=Query(
            default=None,
            alias=alias,
            title=field_info.title,
            description=field_info.description,
            **extra,
        ),
    )
