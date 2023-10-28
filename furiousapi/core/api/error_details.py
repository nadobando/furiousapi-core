from __future__ import annotations

from typing import List, Optional, Union

from pydantic import BaseModel, Field
from starlette import status as http_status

from furiousapi.core.db.models import FuriousModel


class ErrorParameter(FuriousModel):
    name: str = Field(
        ...,
        title="Parameter Name",
        description="Parameter name use for input",
    )
    value: Union[dict, str, BaseModel] = Field(  # keep BaseModel last for annotation not for parsing
        ...,
        title="Parameter Value",
        description="Parameter value",
    )


class ErrorDetails(FuriousModel):
    detail: str = Field(
        ...,
        title="Error text message",
        example="Could not locate external req id REQ9090F",
        description="A human-readable explanation of the error",
    )
    tracking: Optional[str] = Field(
        None,
        title="Tracking ID",
        example="67cb1806-768b-4515-81fe-ab77716ac3ea",
        description="A session tracking ID",
    )


class HttpErrorDetails(ErrorDetails):
    status: int = Field(
        ...,
        title="HTTP status code",
        example="4XX / 5XX",
        description="http error status code 4XX or 5XX",
    )
    type: Optional[str] = Field(
        "apiError",
        title="Error type",
        example="apiError",
        description="Identifies the error type",
    )
    title: Optional[str] = Field(
        None,
        title="Error text message",
        example="Not found",
        description="A brief, human-readable message about the error",
    )
    parameters: Optional[List[ErrorParameter]] = Field(
        None,
        title="Error parameters",
        example="[{name:externalReqId,value:REQ9090F}]",
        description=(
            "Optional field that may contains additional information. The structure is error field name coupled with"
            " the value error"
        ),
    )


class BadRequestHttpErrorDetails(HttpErrorDetails):
    status: int = Field(
        http_status.HTTP_400_BAD_REQUEST,
        title="HTTP Bad Request",
        example="400",
        description="HTTP bad request error status code",
    )
    type: Optional[str] = Field(
        "badRequestError",
        title="Error type",
        example="badRequestError",
        description="Identifies the error type",
    )
    detail: str = Field(
        ...,
        title="Error text message",
        example="The server cannot or will not process the request due to an apparent client error",
        description="A human-readable explanation of the error",
    )
    title: Optional[str] = Field(
        None,
        title="Error text message",
        example="Bad Request Error",
        description="A brief, human-readable message about the error",
    )


class UnauthorizedHttpErrorDetails(HttpErrorDetails):
    status: int = Field(
        http_status.HTTP_401_UNAUTHORIZED,
        title="HTTP Unauthorized",
        example="401",
        description="HTTP unauthorized error status code",
    )
    type: Optional[str] = Field(
        "authenticationError",
        title="Error type",
        example="authenticationError",
        description="Identifies the error type",
    )
    detail: str = Field(
        ...,
        title="Error text message",
        example=(
            "Similar to 403 Forbidden, but specifically for use when authentication is required and has failed or has"
            " not yet been provided"
        ),
        description="A human-readable explanation of the error",
    )
    title: Optional[str] = Field(
        None,
        title="Error text message",
        example="Unauthorized Error",
        description="A brief, human-readable message about the error",
    )


class ForbiddenHttpErrorDetails(HttpErrorDetails):
    status: int = Field(
        http_status.HTTP_403_FORBIDDEN,
        title="HTTP Forbidden",
        example="403",
        description="HTTP forbidden error status code",
    )
    type: Optional[str] = Field(
        "forbiddenError",
        title="Error type",
        example="forbiddenError",
        description="Identifies the error type",
    )
    detail: str = Field(
        ...,
        title="Error text message",
        example="The request contained valid data and was understood by the server, but the server is refusing action",
        description="A human-readable explanation of the error",
    )
    title: Optional[str] = Field(
        None,
        title="Error text message",
        example="Forbidden Error",
        description="A brief, human-readable message about the error",
    )


class NotFoundHttpErrorDetails(HttpErrorDetails):
    status: int = Field(
        http_status.HTTP_404_NOT_FOUND,
        title="HTTP Not Found",
        example="404",
        description="HTTP not found error status code",
    )
    type: Optional[str] = Field(
        "notFoundError",
        title="Error type",
        example="notFoundError",
        description="Identifies the error type",
    )
    detail: str = Field(
        ...,
        title="Error text message",
        example="The requested resource could not be found but may be available in the future",
        description="A human-readable explanation of the error",
    )
    title: Optional[str] = Field(
        None,
        title="Error text message",
        example="Not Found Error",
        description="A brief, human-readable message about the error",
    )


class MethodNotAllowedHttpErrorDetails(HttpErrorDetails):
    status: int = Field(
        http_status.HTTP_405_METHOD_NOT_ALLOWED,
        title="HTTP Method Not Allowed",
        example="405",
        description="HTTP method not allowed error status code",
    )
    type: Optional[str] = Field(
        "methodNotAllowedError",
        title="Error type",
        example="methodNotAllowedError",
        description="Identifies the error type",
    )
    detail: str = Field(
        "Method Not Allowed",
        title="Error text message",
        example="The request was well-formed but was unable to be followed due to semantic errors",
        description="A human-readable explanation of the error",
    )
    title: Optional[str] = Field(
        None,
        title="Error text message",
        example="Method Not Allowed Error",
        description="A brief, human-readable message about the error",
    )


class ConflictHttpErrorDetails(HttpErrorDetails):
    status: int = Field(
        http_status.HTTP_409_CONFLICT,
        title="HTTP Method Conflict",
        example="409",
        description="HTTP method conflict error status code",
    )
    type: Optional[str] = Field(
        "conflictError",
        title="Error type",
        example="conflictError",
        description="Identifies the error type",
    )
    detail: str = Field(
        ...,
        title="Error text message",
        example="The request could not be processed because of conflict in the current state of the resource",
        description="A human-readable explanation of the error",
    )
    title: Optional[str] = Field(
        None,
        title="Error text message",
        example="Conflict Error",
        description="A brief, human-readable message about the error",
    )


class UnprocessableEntityHttpErrorDetails(HttpErrorDetails):
    status: int = Field(
        http_status.HTTP_422_UNPROCESSABLE_ENTITY,
        title="Input Validation Error",
        example="422",
        description="The request was well-formed but was unable to be followed due to semantic errors",
    )
    type: Optional[str] = Field(
        "unprocessableEntityError",
        title="Error type",
        example="unprocessableEntityError",
        description="Identifies the error type",
    )
    detail: str = Field(
        ...,
        title="Error text message",
        example="The request was well-formed but was unable to be followed due to semantic errors",
        description="A human-readable explanation of the error",
    )
    title: Optional[str] = Field(
        None,
        title="Error text message",
        example="Unprocessable Entity Error",
        description="A brief, human-readable message about the error",
    )


class FailedDependencyHttpErrorDetails(HttpErrorDetails):
    status: int = Field(
        http_status.HTTP_424_FAILED_DEPENDENCY,
        title="Failed Dependency",
        example="424",
        description="HTTP the user has sent too many requests in a given amount of time",
    )
    type: Optional[str] = Field(
        "failedDependencyError",
        title="Error type",
        example="failedDependencyError",
        description="Identifies the error type",
    )
    detail: str = Field(
        "The request failed because it depended on another request and that request failed.",
        title="Error text message",
        example="The request failed because it depended on another request and that request failed.",
        description="A human-readable explanation of the error",
    )
    title: Optional[str] = Field(
        None,
        title="Error text message",
        example="Failed Dependency",
        description="A brief, human-readable message about the error",
    )


class TooManyRequestsHttpErrorDetails(HttpErrorDetails):
    status: int = Field(
        http_status.HTTP_429_TOO_MANY_REQUESTS,
        title="HTTP Too Many Requests",
        example="429",
        description="HTTP the user has sent too many requests in a given amount of time",
    )
    type: Optional[str] = Field(
        "rateLimitError",
        title="Error type",
        example="rateLimitError",
        description="Identifies the error type",
    )
    detail: str = Field(
        "Request quota exceeded",
        title="Error text message",
        example="The user has sent too many requests in a given amount of time",
        description="A human-readable explanation of the error",
    )
    title: Optional[str] = Field(
        None,
        title="Error text message",
        example="Too Many Requests Error",
        description="A brief, human-readable message about the error",
    )


class InternalServerHttpErrorDetails(HttpErrorDetails):
    status: int = Field(
        http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="HTTP Internal Server Error",
        example="500",
        description=(
            "HTTP Internal Server Error the server encountered an unexpected condition that prevented it from"
            " fulfilling the request"
        ),
    )
    type: Optional[str] = Field(
        "internalServerError",
        title="Error type",
        example="internalServerError",
        description="Identifies the error type",
    )
    detail: str = Field(
        "The server encountered an unexpected condition that prevented it from fulfilling the request",
        title="Error text message",
        example="The server encountered an unexpected condition that prevented it from fulfilling the request",
        description="A human-readable explanation of the error",
    )
    title: Optional[str] = Field(
        "Internal Server Error",
        title="Error text message",
        example="Internal Server Error",
        description="A brief, human-readable message about the error",
    )


class RequestTimeoutHttpErrorDetails(HttpErrorDetails):
    status: int = Field(
        504,
        title="HTTP Request Timeout",
        example="504",
        description="HTTP request timeout error status code",
    )
    type: Optional[str] = Field(
        "requestTimeoutError",
        title="Error type",
        example="requestTimeoutError",
        description="Identifies the error type",
    )
    detail: str = Field(
        "Request Timeout Error",
        title="Error text message",
        example="The request was well-formed but was unable to be followed due to semantic errors",
        description="A human-readable explanation of the error",
    )
    title: Optional[str] = Field(
        "Request Timeout Error",
        title="Error text message",
        example="Method Not Allowed Error",
        description="A brief, human -readable message about the error",
    )
