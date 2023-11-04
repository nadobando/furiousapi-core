from typing import TYPE_CHECKING, Any, Type

from furiousapi.core.exceptions import FuriousError

if TYPE_CHECKING:
    from pydantic import BaseModel


class FuriousEntityError(FuriousError):
    def __init__(self, model: Type["BaseModel"], **kwargs):
        self.model = model
        super().__init__(model)


class EntityNotFoundError(FuriousEntityError):
    def __init__(self, model: Type["BaseModel"], id_: Any):
        super().__init__(model)
        self.id = id_

    def __str__(self) -> str:
        return f"{self.model} with {self.id} not found"


class EntityAlreadyExistsError(FuriousEntityError):
    def __init__(self, model: Type["BaseModel"], id_: Any):
        super().__init__(model)
        self.id = id_

    def __str__(self) -> str:
        return f"{self.model} with {self.id} already exists"


class FuriousBulkError(FuriousEntityError):
    pass
