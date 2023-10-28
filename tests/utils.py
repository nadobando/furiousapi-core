from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional, Type

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest
    from pydantic import BaseModel


def get_first_doc_from_cache(request: FixtureRequest, cache_key: str, model: Optional[Type[BaseModel]] = None):
    docs = request.config.cache.get(cache_key, None)
    if not (docs and docs):
        return None
    first_doc_json_string = docs[0]
    return model.parse_raw(first_doc_json_string) if model else json.loads(first_doc_json_string)
