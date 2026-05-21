import logging
from typing import Any

from furiousapi.pydantic import PYDANTIC_V2

if PYDANTIC_V2:
    from pydantic import BaseModel, ConfigDict, Extra
else:
    from pydantic import BaseConfig, BaseModel, Extra

try:
    from orjson import orjson  # type: ignore[import-not-found]

    def orjson_dumps(v: Any, *, default: Any = None) -> str:
        return orjson.dumps(v, default=default).decode()

    json_loads = orjson.loads
    json_dumps = orjson_dumps
except ImportError:
    import json

    json_loads = json.loads
    json_dumps = json.dumps  # type: ignore[assignment]

logger = logging.getLogger(__name__)

if PYDANTIC_V2:
    FuriousPydanticConfig = ConfigDict()
else:

    class FuriousPydanticConfig(BaseConfig):
        extra = Extra.allow
        json_dumps = json_dumps
        json_loads = json_loads


class FuriousModel(BaseModel):
    if PYDANTIC_V2:
        model_config = FuriousPydanticConfig
    else:

        class Config(FuriousPydanticConfig): ...  # type: ignore[valid-type,misc]
