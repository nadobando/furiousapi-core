from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from furiousapi.api import error_responses
from furiousapi.core.exceptions import FuriousError


class FuriousAPIError(HTTPException, FuriousError):
    def __init__(self, details: error_responses.HttpErrorResponse, headers: Optional[Dict[str, Any]] = None) -> None:
        HTTPException.__init__(self, status_code=details.status, detail=details.dict(by_alias=True), headers=headers)


# 400
class BadRequestError(FuriousAPIError):
    def __init__(
        self,
        message: str,
        headers: Optional[Dict[str, Any]] = None,
        parameters: Optional[List[error_responses.Parameter]] = None,
    ) -> None:
        details = error_responses.BadRequestHttpErrorResponse(
            detail=message,
            parameters=parameters,
        )
        super().__init__(details=details, headers=headers)


# 401
class UnauthorizedError(FuriousAPIError):
    def __init__(self, headers: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            details=error_responses.UnauthorizedHttpErrorDetails(
                detail="Authentication details were not provided in request",
            ),
            headers=headers,
        )


# 403
class ForbiddenError(FuriousAPIError):
    def __init__(
        self,
        message: str = "The token used is not allowed to make changes",
        headers: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            details=error_responses.ForbiddenHttpErrorDetails(detail=message),
            headers=headers,
        )


# 404
class ResourceNotFoundError(FuriousAPIError):
    def __init__(
        self,
        resource: str,
        headers: Optional[Dict[str, Any]] = None,
        parameters: Optional[List[error_responses.Parameter]] = None,
    ) -> None:
        details = error_responses.NotFoundHttpErrorDetails(
            detail=f"The provided {resource} does not exist in our system",
            parameters=parameters,
        )
        super().__init__(details=details, headers=headers)


# 405
class MethodNotAllowedError(FuriousAPIError):
    def __init__(self, headers: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(details=error_responses.MethodNotAllowedHttpErrorDetails(), headers=headers)


# 409
class ConflictError(FuriousAPIError):
    def __init__(
        self,
        message: str,
        headers: Optional[Dict[str, Any]] = None,
        parameters: Optional[List[error_responses.Parameter]] = None,
    ) -> None:
        super().__init__(
            details=error_responses.ConflictHttpErrorDetails(detail=message, parameters=parameters),
            headers=headers,
        )


# 422
class UnprocessableEntityError(FuriousAPIError):
    def __init__(
        self,
        entity: str,
        headers: Optional[Dict[str, Any]] = None,
        parameters: Optional[List[error_responses.Parameter]] = None,
    ) -> None:
        super().__init__(
            details=error_responses.UnprocessableEntityHttpErrorDetails(
                detail=f"unprocessable entity: {entity}",
                parameters=parameters,
            ),
            headers=headers,
        )


# 424
class FailedDependencyError(FuriousAPIError):
    def __init__(
        self,
        message: str = "",
        headers: Optional[Dict[str, Any]] = None,
        parameters: Optional[List[error_responses.Parameter]] = None,
    ) -> None:
        super().__init__(
            details=error_responses.FailedDependencyHttpErrorDetails(
                detail=message,
                parameters=parameters,
            ),
            headers=headers,
        )


# 429
class TooManyRequestsError(FuriousAPIError):
    def __init__(self, headers: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(details=error_responses.TooManyRequestsHttpErrorDetails(), headers=headers)


# 500
class InternalServerError(FuriousAPIError):
    def __init__(self, headers: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(details=error_responses.InternalServerHttpErrorDetails(), headers=headers)


# 504
class RequestTimeoutError(FuriousAPIError):
    def __init__(self, headers: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(details=error_responses.RequestTimeoutHttpErrorDetails(), headers=headers)
