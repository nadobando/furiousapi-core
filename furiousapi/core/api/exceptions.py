from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from furiousapi.core.api import error_details
from furiousapi.core.exceptions import FuriousError


class FuriousAPIError(HTTPException, FuriousError):
    def __init__(self, details: error_details.HttpErrorDetails, headers: Optional[Dict[str, Any]] = None) -> None:
        HTTPException.__init__(self, status_code=details.status, detail=details.dict(by_alias=True), headers=headers)


# 400
class BadRequestHttpError(FuriousAPIError):
    def __init__(
        self,
        message: str,
        headers: Optional[Dict[str, Any]] = None,
        parameters: Optional[List[error_details.ErrorParameter]] = None,
    ) -> None:
        details = error_details.BadRequestHttpErrorDetails(
            detail=message,
            parameters=parameters,
        )
        super().__init__(details=details, headers=headers)


# 401
class UnauthorizedHttpError(FuriousAPIError):
    def __init__(self, headers: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            details=error_details.UnauthorizedHttpErrorDetails(
                detail="Authentication details were not provided in request",
            ),
            headers=headers,
        )


# 403
class ForbiddenHttpError(FuriousAPIError):
    def __init__(
        self,
        message: str = "The token used is not allowed to make changes",
        headers: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            details=error_details.ForbiddenHttpErrorDetails(detail=message),
            headers=headers,
        )


# 404
class ResourceNotFoundHttpError(FuriousAPIError):
    def __init__(
        self,
        resource: str,
        headers: Optional[Dict[str, Any]] = None,
        parameters: Optional[List[error_details.ErrorParameter]] = None,
    ) -> None:
        details = error_details.NotFoundHttpErrorDetails(
            detail=f"The provided {resource} does not exist in our system",
            parameters=parameters,
        )
        super().__init__(details=details, headers=headers)


# 405
class MethodNotAllowedHttpError(FuriousAPIError):
    def __init__(self, headers: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(details=error_details.MethodNotAllowedHttpErrorDetails(), headers=headers)


# 409
class ConflictHttpError(FuriousAPIError):
    def __init__(
        self,
        message: str,
        headers: Optional[Dict[str, Any]] = None,
        parameters: Optional[List[error_details.ErrorParameter]] = None,
    ) -> None:
        super().__init__(
            details=error_details.ConflictHttpErrorDetails(detail=message, parameters=parameters),
            headers=headers,
        )


# 422
class UnprocessableEntityHttpError(FuriousAPIError):
    def __init__(
        self,
        entity: str,
        headers: Optional[Dict[str, Any]] = None,
        parameters: Optional[List[error_details.ErrorParameter]] = None,
    ) -> None:
        super().__init__(
            details=error_details.UnprocessableEntityHttpErrorDetails(
                detail=f"unprocessable entity: {entity}",
                parameters=parameters,
            ),
            headers=headers,
        )


# 424
class FailedDependencyHttpError(FuriousAPIError):
    def __init__(
        self,
        message: str = "",
        headers: Optional[Dict[str, Any]] = None,
        parameters: Optional[List[error_details.ErrorParameter]] = None,
    ) -> None:
        super().__init__(
            details=error_details.FailedDependencyHttpErrorDetails(
                detail=message,
                parameters=parameters,
            ),
            headers=headers,
        )


# 429
class TooManyRequestsHttpError(FuriousAPIError):
    def __init__(self, headers: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(details=error_details.TooManyRequestsHttpErrorDetails(), headers=headers)


# 500
class InternalServerError(FuriousAPIError):
    def __init__(self, headers: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(details=error_details.InternalServerHttpErrorDetails(), headers=headers)


# 504
class RequestTimeoutHttpError(FuriousAPIError):
    def __init__(self, headers: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(details=error_details.RequestTimeoutHttpErrorDetails(), headers=headers)
