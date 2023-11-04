from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Annotated, Any, Dict, List, Literal, Optional, Union

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.background import BackgroundTask


class PartialModelResponse(JSONResponse):
    def __init__(
        self,
        content: Optional[BaseModel],
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        media_type: Optional[str] = None,
        background: Optional[BackgroundTask] = None,
    ) -> None:
        content = jsonable_encoder(content, by_alias=True)
        super().__init__(content, status_code, headers, media_type, background)


class BulkItemStatusEnum(str, Enum):
    OK = "OK"
    ERROR = "ERROR"


class BulkCreateResponse(BaseModel):
    status: BulkItemStatusEnum


class BulkItemSuccess(BaseModel):
    status: Optional[Literal[BulkItemStatusEnum.OK]] = Field(default=BulkItemStatusEnum.OK)
    id: Any


class BulkItemError(BaseModel):
    status: Optional[Literal[BulkItemStatusEnum.ERROR]] = Field(default=BulkItemStatusEnum.ERROR)
    message: str


BulkResponseModelUnion = Union[BulkItemError, BulkItemSuccess]

BulkItemResult = Annotated[BulkResponseModelUnion, Field(discriminator="status")]


class BulkResponseModel(BaseModel):
    items: List[BulkItemResult]
    has_errors: bool = False
