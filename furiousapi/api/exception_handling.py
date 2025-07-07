from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Type

if TYPE_CHECKING:
    from starlette.requests import Request

from starlette.responses import JSONResponse

from furiousapi.api.exceptions import (
    ConflictError,
    FuriousAPIError,
    ResourceNotFoundError,
)
from furiousapi.db.exceptions import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    FuriousEntityError,
)

DB_TO_HTTP_ERROR: Dict[Type[FuriousEntityError], Type] = {
    EntityNotFoundError: ResourceNotFoundError,
    EntityAlreadyExistsError: ConflictError,
}

logger = logging.getLogger(__name__)


def furious_db_exception_handler(_: Request, exception: FuriousEntityError) -> JSONResponse:
    api_exception: FuriousAPIError = DB_TO_HTTP_ERROR[exception.__class__](str(exception))
    logger.info("furiousapi error", exc_info=True)
    return JSONResponse(
        content=api_exception.detail, status_code=api_exception.status_code, headers=api_exception.headers
    )


def furious_api_exception_handler(_: Request, exception: FuriousAPIError) -> JSONResponse:
    return JSONResponse(content=exception.detail, status_code=exception.status_code, headers=exception.headers)
