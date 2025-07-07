from __future__ import annotations

from typing import Any, Type, get_args, get_origin


def get_most_inner_class(annotation: Any) -> Type | None:
    """
    Recursively retrieves the most inner class from a type annotation.

    Args:
        annotation: The type annotation to inspect.

    Returns:
        The most inner class/type.
    """
    origin = get_origin(annotation)  # Extract the base of the type
    args = get_args(annotation)  # Extract the arguments (if any)

    if origin is None and not args:
        # Base case: This is the most inner type
        return annotation

    # Recursively process the arguments
    for arg in args:
        inner_class = get_most_inner_class(arg)
        if inner_class is not None:
            return inner_class

    return None
