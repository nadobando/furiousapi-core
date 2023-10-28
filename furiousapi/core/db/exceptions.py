from typing import TYPE_CHECKING, Type

from furiousapi.core.exceptions import FuriousError

if TYPE_CHECKING:
    from pydantic import BaseModel


class FuriousEntityError(FuriousError):
    pass


class EntityNotFoundError(FuriousEntityError):
    pass


class EntityAlreadyExistsError(FuriousEntityError):
    def __init__(self, model: Type["BaseModel"]):
        self.model = model
        super().__init__(f"{self.model.__name__} entity already exists")


class FuriousBulkError(FuriousEntityError):
    pass
