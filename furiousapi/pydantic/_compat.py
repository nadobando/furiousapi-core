from fastapi._compat import PYDANTIC_V2, FieldInfo, ModelField

if PYDANTIC_V2:
    from pydantic._internal._model_construction import ModelMetaclass
    from pydantic.networks import _BaseMultiHostUrl as MultiHostDsn
    from pydantic_settings import BaseSettings
else:
    from pydantic import BaseSettings
    from pydantic.main import ModelMetaclass
    from pydantic.networks import MultiHostDsn

__all__ = ["PYDANTIC_V2", "BaseSettings", "FieldInfo", "ModelField", "ModelMetaclass", "MultiHostDsn"]
