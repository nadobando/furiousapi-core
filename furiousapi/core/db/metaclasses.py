import inspect
import logging
from typing import Any, Dict, Tuple, Type

import pydantic
from fastapi import Depends, Query, params
from pydantic import BaseModel

from .utils import _convert_pydantic, _remove_extra_data_from_signature, clean_dict

logger = logging.getLogger(__name__)


class AllOptionalMeta(pydantic.main.ModelMetaclass):
    def __new__(mcs, name: str, bases: Tuple[type], namespaces: Dict[str, Any], **kwargs) -> Type[BaseModel]:
        _convert_pydantic(name, namespaces, bases)
        new = super().__new__(mcs, name, bases, namespaces, **kwargs)
        _remove_extra_data_from_signature(new)
        return new


def model_query(model: Type[BaseModel], meta: Type[pydantic.main.ModelMetaclass] = AllOptionalMeta) -> params.Depends:
    cls = meta(f"Optional{model.__name__}", (model,), {})

    def dependency(**kwargs) -> BaseModel:
        return cls(**clean_dict(kwargs))

    cls_params = dict(cls.__signature__.parameters)
    cls_params.pop("args", None)
    params = []
    for parameter, model_field in zip(cls_params.values(), model.__fields__.values()):
        params.append(
            inspect.Parameter(
                name=parameter.name,
                kind=parameter.kind,
                annotation=parameter.annotation,
                default=Query(
                    default=model_field.default,
                    alias=model_field.field_info.alias,
                    title=model_field.field_info.title,
                    description=model_field.field_info.description,
                    **model_field.field_info.extra,
                ),
            ),
        )

    dependency.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        parameters=params,
        return_annotation=model,
        __validate_parameters__=True,
    )

    return Depends(dependency)
