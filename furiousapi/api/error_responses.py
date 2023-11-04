from __future__ import annotations

from typing import List, Optional, Union

from pydantic import BaseModel, Field
from starlette import status as http_status

from furiousapi.db.models import FuriousModel


class Parameter(FuriousModel):
    name: str
    value: Union[dict, str, BaseModel]


class ErrorResponse(FuriousModel):
    detail: str


class HttpErrorResponse(ErrorResponse):
    status: int = Field(..., title="HTTP status code")
    title: Optional[str]
    parameters: Optional[List[Parameter]] = Field(None, title="Error parameters")


class BadRequestHttpErrorResponse(HttpErrorResponse):
    status: int = Field(http_status.HTTP_400_BAD_REQUEST, title="HTTP Bad Request")
    title: str = "Bad Request Error"
    detail: str


class UnauthorizedHttpErrorDetails(HttpErrorResponse):
    status: int = Field(http_status.HTTP_401_UNAUTHORIZED, title="HTTP Unauthorized")
    title: str = "Unauthorized Error"
    detail: str = "Unauthorized"


class ForbiddenHttpErrorDetails(HttpErrorResponse):
    status: int = Field(http_status.HTTP_403_FORBIDDEN, title="HTTP Forbidden")
    title: str = "Forbidden Error"
    detail: str = "The request contained valid data and was understood by the server, but the server is refusing action"


class NotFoundHttpErrorDetails(HttpErrorResponse):
    status: int = Field(http_status.HTTP_404_NOT_FOUND, title="HTTP Not Found")
    title: str = "Not Found Error"
    detail: str = "The requested resource could not be found but may be available in the future"


class MethodNotAllowedHttpErrorDetails(HttpErrorResponse):
    status: int = Field(http_status.HTTP_405_METHOD_NOT_ALLOWED, title="HTTP Method Not Allowed")
    title: str = "Method Not Allowed Error"
    detail: str = "Method Not Allowed"


class ConflictHttpErrorDetails(HttpErrorResponse):
    status: int = Field(http_status.HTTP_409_CONFLICT, title="HTTP Method Conflict")
    title: str = "Conflict Error"
    detail: str = "The request could not be processed because of conflict in the current state of the resource"


class UnprocessableEntityHttpErrorDetails(HttpErrorResponse):
    status: int = Field(http_status.HTTP_422_UNPROCESSABLE_ENTITY, title="Input Validation Error")
    title: str = "Unprocessable Entity Error"
    detail: str = "The request was well-formed but was unable to be followed due to semantic errors"


class FailedDependencyHttpErrorDetails(HttpErrorResponse):
    status: int = Field(http_status.HTTP_424_FAILED_DEPENDENCY, title="Failed Dependency")
    title: str = "Failed Dependency"
    detail: str = "The request failed because it depended on another request and that request failed."


class TooManyRequestsHttpErrorDetails(HttpErrorResponse):
    status: int = Field(http_status.HTTP_429_TOO_MANY_REQUESTS, title="HTTP Too Many Requests")
    title: str = "Too Many Requests Error"
    detail: str = "The user has sent too many requests in a given amount of time"


class InternalServerHttpErrorDetails(HttpErrorResponse):
    status: int = Field(http_status.HTTP_500_INTERNAL_SERVER_ERROR, title="HTTP Internal Server Error")
    title: str = "Internal Server Error"
    detail: str = "The server encountered an unexpected condition that prevented it from fulfilling the request"


class RequestTimeoutHttpErrorDetails(HttpErrorResponse):
    status: int = Field(504, title="HTTP Request Timeout")
    title: str = "Request Timeout Error"
    detail: str = "Request Timeout Error"
