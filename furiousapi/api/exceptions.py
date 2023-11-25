from typing import Any, Dict, Optional

from fastapi import HTTPException

from furiousapi.api import error_responses
from furiousapi.core.exceptions import FuriousError


class FuriousAPIError(HTTPException, FuriousError):
    def __init__(
        self,
        error_response: error_responses.HttpErrorResponse,
        headers: Optional[Dict[str, Any]] = None,
    ) -> None:
        HTTPException.__init__(
            self, status_code=error_response.status_code, detail=error_response.dict(by_alias=True), headers=headers
        )


# 400
class BadRequestError(FuriousAPIError):
    def __init__(self, message: str, headers: Optional[Dict[str, Any]] = None) -> None:
        details = error_responses.BadRequestHttpErrorResponse(detail=message)
        super().__init__(error_response=details, headers=headers)


# 401
class UnauthorizedError(FuriousAPIError):
    def __init__(self, headers: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            error_response=error_responses.UnauthorizedHttpErrorDetails(),
            headers=headers,
        )


# 403
class ForbiddenError(FuriousAPIError):
    def __init__(
        self,
        message: str = "Access Denied - You don't have permission to access",
        headers: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            error_response=error_responses.ForbiddenHttpErrorDetails(detail=message),
            headers=headers,
        )


# 404
class ResourceNotFoundError(FuriousAPIError):
    def __init__(
        self,
        message: str,
        headers: Optional[Dict[str, Any]] = None,
    ) -> None:
        details = error_responses.NotFoundHttpErrorDetails(detail=message)
        super().__init__(error_response=details, headers=headers)


# 405
class MethodNotAllowedError(FuriousAPIError):
    def __init__(self, headers: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(error_response=error_responses.MethodNotAllowedHttpErrorDetails(), headers=headers)


# 409
class ConflictError(FuriousAPIError):
    def __init__(
        self,
        message: str,
        headers: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            error_response=error_responses.ConflictHttpErrorDetails(detail=message),
            headers=headers,
        )


# 422
class UnprocessableEntityError(FuriousAPIError):
    def __init__(
        self,
        entity: str,
        headers: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            error_response=error_responses.UnprocessableEntityHttpErrorDetails(
                detail=f"unprocessable entity: {entity}"
            ),
            headers=headers,
        )


# 424
class FailedDependencyError(FuriousAPIError):
    def __init__(
        self,
        message: str = "",
        headers: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            error_response=error_responses.FailedDependencyHttpErrorDetails(
                detail=message,
            ),
            headers=headers,
        )


# 429
class TooManyRequestsError(FuriousAPIError):
    def __init__(self, headers: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(error_response=error_responses.TooManyRequestsHttpErrorDetails(), headers=headers)


# 500
class InternalServerError(FuriousAPIError):
    def __init__(self, headers: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(error_response=error_responses.InternalServerHttpErrorDetails(), headers=headers)


# 504
class RequestTimeoutError(FuriousAPIError):
    def __init__(self, headers: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(error_response=error_responses.RequestTimeoutHttpErrorDetails(), headers=headers)
