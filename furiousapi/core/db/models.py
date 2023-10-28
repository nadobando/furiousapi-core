import logging
from typing import Any

from pydantic import BaseConfig, BaseModel, Extra

try:
    from orjson import orjson

    def orjson_dumps(v: Any, *, default: Any = None) -> str:
        return orjson.dumps(v, default=default).decode()

    json_loads = orjson.loads
    json_dumps = orjson_dumps
except ImportError:
    import json

    json_loads = json.loads
    json_dumps = json.dumps  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class FuriousPydanticConfig(BaseConfig):
    extra = Extra.allow
    json_dumps = json_dumps
    json_loads = json_loads


class FuriousModel(BaseModel):
    class Config(FuriousPydanticConfig): ...
