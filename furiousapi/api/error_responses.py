from __future__ import annotations

from pydantic import Field
from starlette import status as http_status

from furiousapi.db.models import FuriousModel


class HttpErrorResponse(FuriousModel):
    status_code: int = Field(..., title="HTTP status code")
    detail: str = Field(..., title="Reason for the error")


class BadRequestHttpErrorResponse(HttpErrorResponse):
    status_code: int = Field(http_status.HTTP_400_BAD_REQUEST, title="HTTP Bad Request")
    detail: str = (
        "The server could not process the request due to a client error, such as bad syntax or deceptive routing."
    )


class UnauthorizedHttpErrorDetails(HttpErrorResponse):
    status_code: int = Field(http_status.HTTP_401_UNAUTHORIZED, title="HTTP Unauthorized")
    detail: str = "Insufficient permissions."


class ForbiddenHttpErrorDetails(HttpErrorResponse):
    status_code: int = Field(http_status.HTTP_403_FORBIDDEN, title="HTTP Forbidden")
    detail: str = "Access Denied - You don't have permission to access."


class NotFoundHttpErrorDetails(HttpErrorResponse):
    status_code: int = Field(http_status.HTTP_404_NOT_FOUND, title="HTTP Not Found")
    detail: str = "The requested resource could not be found."


class MethodNotAllowedHttpErrorDetails(HttpErrorResponse):
    status_code: int = Field(http_status.HTTP_405_METHOD_NOT_ALLOWED, title="HTTP Method Not Allowed")
    detail: str = "The requested method is not allowed"


class ConflictHttpErrorDetails(HttpErrorResponse):
    status_code: int = Field(http_status.HTTP_409_CONFLICT, title="HTTP Method Conflict")
    detail: str = "The request could not be processed because of conflict in the current state of the resource"


class UnprocessableEntityHttpErrorDetails(HttpErrorResponse):
    status_code: int = Field(http_status.HTTP_422_UNPROCESSABLE_ENTITY, title="Input Validation Error")
    detail: str = "The request was well-formed but was unable to be followed due to semantic errors"


class FailedDependencyHttpErrorDetails(HttpErrorResponse):
    status_code: int = Field(http_status.HTTP_424_FAILED_DEPENDENCY, title="Failed Dependency")
    detail: str = "The request failed due to failure of a previous request."


class TooManyRequestsHttpErrorDetails(HttpErrorResponse):
    status_code: int = Field(http_status.HTTP_429_TOO_MANY_REQUESTS, title="HTTP Too Many Requests")
    detail: str = "The user has sent too many requests in a given amount of time."


class InternalServerHttpErrorDetails(HttpErrorResponse):
    status_code: int = Field(http_status.HTTP_500_INTERNAL_SERVER_ERROR, title="HTTP Internal Server Error")
    detail: str = "The server encountered an unexpected condition that prevented it from fulfilling the request."


class RequestTimeoutHttpErrorDetails(HttpErrorResponse):
    status_code: int = Field(504, title="HTTP Request Timeout")
    detail: str = "Request Timeout Error"
