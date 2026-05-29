"""Service layer for furiousapi.

``BaseService`` is the abstract root of the service hierarchy.
``ModelService[TEntity]`` is the CRUD convenience over a ``BaseRepository[T]``,
shipping default events (``Created``/``Updated``/``Deleted``) parametrized per
service entity. ``BaseEvent`` is the pydantic event base; subclass with
``wraps=`` (or decorate a method with ``@SomeEvent``) to bind an event.
"""

from furiousapi.service.base import BaseService, ModelService, ServiceMeta
from furiousapi.service.events import (
    BaseEvent,
    Created,
    Deleted,
    EventMeta,
    EventsDict,
    ModelEventsDict,
    MultipleHookErrorSinksWarning,
    Updated,
    WrapsOnlyWiringWarning,
)
from furiousapi.service.mixin import BaseServiceMixin

__all__ = [
    "BaseEvent",
    "BaseService",
    "BaseServiceMixin",
    "Created",
    "Deleted",
    "EventMeta",
    "EventsDict",
    "ModelEventsDict",
    "ModelService",
    "MultipleHookErrorSinksWarning",
    "ServiceMeta",
    "Updated",
    "WrapsOnlyWiringWarning",
]
