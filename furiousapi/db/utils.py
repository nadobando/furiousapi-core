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
    cast,
)

from fastapi import Query
from pydantic import BaseConfig, BaseModel, Extra, create_model
from pydantic.fields import FieldInfo

from furiousapi.utils import NOT_SET, NotSet

from .consts import ANNOTATIONS
from .fields import SortableFieldEnum

if TYPE_CHECKING:
    from pydantic.fields import ModelField

logger = logging.getLogger(__name__)


def get_model_fields(
    model: Type[BaseModel], include: Optional[Set[str]] = None, *, recursive: bool = False
) -> Dict[str, str]:
    keys = {}
    config = model.Config  # type: ignore[attr-defined]
    alias_generator = getattr(config, "alias_generator", lambda x: x) or (lambda x: x)
    for key, value in model.__fields__.items():
        # if recursive and isinstance(value.type_, GenericAlias) and value.type_.__origin__ is list:
        #     pass
        if recursive and issubclass(value.type_, BaseModel):
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


def get_model_sort_fields_enum(
    model: Type[BaseModel],
    override_name: Optional[str] = None,
    include: Optional[Set[str]] = None,
    exclude: Optional[Set[str]] = None,
) -> Type[SortableFieldEnum]:
    name = override_name or f"{model.__name__}FieldSortEnum"
    fields: Dict[str, str] = get_model_fields(model, include)

    if exclude:
        fields = {k: v for k, v in fields.items() if k not in exclude}

    return SortableFieldEnum(name, cast(List[str], fields))  # type: ignore[call-overload]


if sys.version_info >= (3, 11):
    from typing import NamedTuple
else:
    from typing_extensions import NamedTuple


class FieldAlias(NamedTuple):
    name: str
    field: "ModelField"


@lru_cache
def model_alias_mapping(model: Type[BaseModel]) -> Dict[str, FieldAlias]:
    aliases = {}
    for k, v in model.__fields__.items():
        aliases[v.alias] = FieldAlias(k, v)

    return aliases


Projection = Dict[str, Union[int, "Projection"]]


def create_subset_model(model: Type[BaseModel], projection: Projection) -> Type[BaseModel]:
    """
    Create a new Pydantic model that is a subset of the given model, based on a given projection.

    :param model: The base Pydantic model to create a subset from.
    :type model: Type[BaseModel]
    :param projection: A dictionary defining the subset of fields to include in the new model.
    :type projection: RecursiveDict
    :return: The new Pydantic model that is a subset of the original model.
    :rtype: Type[BaseModel]

    This function recursively traverses the given projection dictionary
    to build up a new set of fields to include in the subset model.
    The resulting model will have the same structure as the original model, but with only the fields
    specified in the projection included.

    Note that if a field in the projection is itself a Pydantic model, that model will also be included in the subset
    (along with its own subset of fields, if specified in the projection).

    Also note that any fields in the original model that are not included in the projection will not be included in the
    subset model.
    """
    fields: Dict[str, Any] = {}
    alias_mapping = model_alias_mapping(model)
    projection_stack: List[Tuple[Any, Projection, Dict[str, Any]]] = [(model, projection, fields)]

    while projection_stack:
        curr_model, curr_projection, curr_fields = projection_stack.pop()
        for k, v in curr_projection.items():
            if isinstance(v, dict):
                subset_field = curr_model.__fields__.get(k, None)

                if subset_field is not None and issubclass(subset_field.type_, BaseModel):
                    projection_stack.append((subset_field.type_, v, {}))

                field_annotation = subset_field.type_ if subset_field is not None else v
                field_info = None if subset_field is None else subset_field.field_info
                curr_fields[k] = (field_annotation, field_info)

            elif k in curr_model.__fields__ or k in alias_mapping:
                field = curr_model.__fields__.get(k, None)
                if field is None:
                    alias = alias_mapping.get(k)
                    field = alias and alias.field
                if field is not None:
                    field_name = k if k in curr_model.__fields__ else alias_mapping[k].name
                    curr_fields[field_name] = (field.annotation, field.field_info)

    config = BaseConfig
    config.extra = Extra.ignore  # type: ignore[attr-defined]
    return create_model(f"Temp{model.__name__}", __config__=config, **fields)  # type: ignore[call-overload]


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


def init_param(model_field: "ModelField", name: str, alias: str, parameter: inspect.Parameter) -> inspect.Parameter:
    annotation = model_field.annotation
    return inspect.Parameter(
        name=name,
        kind=parameter.kind,
        annotation=annotation,
        default=Query(
            default=None,
            alias=alias,
            title=model_field.field_info.title,
            description=model_field.field_info.description,
            **model_field.field_info.extra,
        ),
    )
