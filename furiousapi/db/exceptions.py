from __future__ import annotations

from typing import TYPE_CHECKING, Any

from furiousapi.core.exceptions import FuriousError

if TYPE_CHECKING:
    from pydantic import BaseModel


class FuriousEntityError(FuriousError):
    def __init__(self, model: type[BaseModel], **kwargs):
        super().__init__()
        self.model = model


class EntityNotFoundError(FuriousEntityError):
    def __init__(self, model: type[BaseModel], id_: Any):
        super().__init__(model)
        self.id = id_

    def __str__(self) -> str:
        return f"{self.model.__name__} with {self.id} not found"


class EntityAlreadyExistsError(FuriousEntityError):
    def __init__(self, model: type[BaseModel], id_: Any):
        super().__init__(model)
        self.id = id_

    def __str__(self) -> str:
        return f"{self.model.__name__} with {self.id} already exists"


class FuriousBulkError(FuriousEntityError):
    pass
