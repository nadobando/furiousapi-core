from typing import Set, Union

from furiousapi.core.exceptions import FuriousError


class FuriousRQLError(FuriousError): ...


class FuriousRQLSyntaxError(SyntaxError, FuriousRQLError):
    pass


class SelectSyntaxError(FuriousRQLSyntaxError):
    pass


class TransformationSyntaxError(FuriousRQLSyntaxError):
    pass


class SelectDotNotationError(SelectSyntaxError):
    def __init__(self):
        super().__init__("Dot notation is not allowed in `select`. Use brackets instead.")


class MismatchedParenthesesError(SelectSyntaxError):
    def __init__(self, query: str):
        super().__init__(f"Mismatched parentheses in: `{query}`. Check for missing or extra parentheses.")


class MismatchedBracketsError(SelectSyntaxError):
    def __init__(self, query: str):
        super().__init__(f"Mismatched brackets in: `{query}`. Check for missing or extra brackets.")


class TransformationInvalidFieldError(TransformationSyntaxError):
    def __init__(self, field: str, query: str):
        super().__init__(f"Invalid field `{field}` in transformation: `{query}`. Check allowed fields.")


class RQLFieldValidationError(FuriousRQLError):
    """Base class for field validation errors in RQL."""

    def __init__(self, field: str, reason: str):
        message = f"Field '{field}': {reason}"
        super().__init__(message)
        self.field = field
        self.reason = reason


# --- Filter validation errors ---
class RQLFilterNotAllowedError(RQLFieldValidationError):
    def __init__(self, field: str, operator: str, allowed_ops: Union[Set, None] = None):
        allowed_msg = f"(allowed: {allowed_ops})" if allowed_ops else "(no filters allowed)"
        reason = f"filter operator '{operator}' is not allowed {allowed_msg}"
        super().__init__(field, reason)


class RQLFilterDeniedError(RQLFieldValidationError):
    def __init__(self, field: str, operator: str):
        reason = f"filter operator '{operator}' is explicitly denied"
        super().__init__(field, reason)


class RQLSortNotAllowedError(RQLFieldValidationError):
    def __init__(self, field: str):
        reason = "sorting by this field is not allowed"
        super().__init__(field, reason)


class RQLSortDeniedError(RQLFieldValidationError):
    def __init__(self, field: str):
        reason = "sorting by this field is denied"
        super().__init__(field, reason)


class RQLSelectNotAllowedError(RQLFieldValidationError):
    def __init__(self, field: str):
        reason = "selection of this field is not allowed"
        super().__init__(field, reason)


class RQLSelectDeniedError(RQLFieldValidationError):
    def __init__(self, field: str):
        reason = "selection of this field is explicitly denied"
        super().__init__(field, reason)
