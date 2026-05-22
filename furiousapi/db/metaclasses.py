from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING, Any

from fastapi import Depends, Query, params

from furiousapi.db.utils import (
    _convert_pydantic,
    _remove_extra_data_from_signature,
    clean_dict,
)
from furiousapi.pydantic import PYDANTIC_V2, ModelMetaclass

if TYPE_CHECKING:
    from pydantic import BaseModel
logger = logging.getLogger(__name__)


class AllOptionalMeta(ModelMetaclass):
    def __new__(mcs, name: str, bases: tuple[type], namespaces: dict[str, Any], **kwargs) -> type[BaseModel]:
        _convert_pydantic(name, namespaces, bases)
        new = super().__new__(mcs, name, bases, namespaces, **kwargs)
        _remove_extra_data_from_signature(new)
        return new


def model_query(model: type[BaseModel], meta: type[ModelMetaclass] = AllOptionalMeta) -> params.Depends:
    cls = meta(f"Optional{model.__name__}", (model,), {})

    def dependency(**kwargs) -> BaseModel:
        return cls(**clean_dict(kwargs))

    cls_params = dict(cls.__signature__.parameters)  # type: ignore[attr-defined]
    cls_params.pop("args", None)
    params = []
    if PYDANTIC_V2:
        for parameter, field_info in zip(cls_params.values(), model.model_fields.values()):
            params.append(
                inspect.Parameter(
                    name=parameter.name,
                    kind=parameter.kind,
                    annotation=parameter.annotation,
                    default=Query(
                        default=field_info.default,
                        alias=field_info.alias,
                        title=field_info.title,
                        description=field_info.description,
                        # **field_info.extra,
                    ),
                ),
            )

    else:
        for parameter, model_field in zip(cls_params.values(), model.__fields__.values()):  # type: ignore[attr-defined]
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
