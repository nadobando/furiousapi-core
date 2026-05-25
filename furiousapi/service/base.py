"""Foundation of the service hierarchy.

* :func:`_extract_model` — internal helper that lifts ``T`` from
  ``BaseService[T].__orig_bases__``.
* :class:`ServiceMeta` — metaclass shared by every service class. Stores the
  lifted ``T`` as ``cls.__model__`` (mirrors ``RepositoryMeta``).
* :class:`BaseService` — abstract root of the service hierarchy. No CRUD
  methods, no FastAPI knowledge, no constructor. Subclasses that need
  dependencies define their own ``__init__``.
* :class:`ModelService` — CRUD pass-through over a ``BaseRepository[TEntity]``.
"""

from __future__ import annotations

from abc import ABCMeta
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel

from furiousapi.service.events import (
    Created,
    Deleted,
    ModelEventsDict,
    RegistryEntry,
    Updated,
    collect_handlers,
    install_wrappers,
    rebind_events,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from enum import Enum

    from furiousapi.api.responses import BulkResponseModel
    from furiousapi.db.repository import BaseRepository


# Bound to BaseModel to match BaseRepository[T: BaseModel] — entities are
# pydantic models throughout the framework.
TEntity = TypeVar("TEntity", bound=BaseModel)


def _extract_model(bases: tuple[type, ...], namespace: dict[str, Any]) -> type | None:
    if not any(isinstance(b, ServiceMeta) for b in bases):
        return None
    orig_bases = namespace.get("__orig_bases__")
    if not orig_bases:
        return None
    args = getattr(orig_bases[0], "__args__", None)
    if not args:
        return None
    model = args[0]
    return None if isinstance(model, TypeVar) else model


class ServiceMeta(ABCMeta):
    """Metaclass for the service hierarchy.

    * Lifts ``T`` from ``ModelService[T].__orig_bases__`` into ``cls.__model__``
      (mirrors ``furiousapi.db.repository.RepositoryMeta``).
    * Collects ``@Event.before/.after/.on_error`` handlers into
      ``cls._event_handlers`` (inheriting parent registries).
    * Installs firing wrappers on methods wired to events via ``wraps=``.

    The handler-collection and wrapper-installation logic lives in
    ``furiousapi.service.events`` (it's event-infrastructure, not
    service-hierarchy); this metaclass just orchestrates the calls.
    """

    _event_handlers: dict[tuple[type, str], list[RegistryEntry]]

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ):
        model = _extract_model(bases, namespace)
        if model is not None:
            namespace = {"__model__": model, **namespace}
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if model is not None:
            # Per-service event identity: rebind Created → Created[Order] etc.
            rebind_events(cls, model)
        cls._event_handlers = collect_handlers(bases, namespace)
        install_wrappers(cls)
        return cls


class BaseService(metaclass=ServiceMeta):
    """Abstract root of the service hierarchy."""


class ModelService(BaseService, Generic[TEntity]):
    """Thin orchestrator over a ``BaseRepository[TEntity]``.

    ``repository`` is the single dependency; pass it via the constructor::

        service = OrderService(repository=order_repo)

    Ships three framework-default event classes (``Created``, ``Updated``,
    ``Deleted``) wired to the matching CRUD methods. Subclasses inherit them.

    **Two wiring sources, intentionally redundant** — each CRUD method below
    carries a visible ``@Created.emitted_by`` / ``@Updated.emitted_by`` /
    ``@Deleted.emitted_by`` decorator AND the event class itself declares
    ``wraps=`` (e.g. ``Created`` has ``wraps="add"``). Both point to the same
    method; the framework dedupes.

    * The ``wraps=`` on the event is the canonical, machine-readable binding
      (used by tooling / introspection, and self-describing for the event).
    * The ``@Event.emitted_by`` decorator on the method is for
      **source-reading visibility** — a reader scanning ``ModelService`` sees
      ``@Created.emitted_by`` right above ``add`` and knows it fires that event.
      It's identity-preserving, so call sites stay type-checked (unlike a bare
      ``@Created``, which pydantic's mypy plugin would mistype).

    Keep them consistent if you override a method's wiring.
    """

    if TYPE_CHECKING:
        __model__: type[TEntity]

    repository: BaseRepository[TEntity]

    events: ModelEventsDict[TEntity] = ModelEventsDict(
        Created=Created,
        Updated=Updated,
        Deleted=Deleted,
    )

    def __init__(self, repository: BaseRepository[TEntity]) -> None:
        self.repository = repository

    async def get(
        self,
        identifiers: int | str | dict[str, Any] | tuple,
        fields: Iterable[Enum] | None = None,
        *,
        should_error: bool = True,
    ) -> TEntity | None:
        return await self.repository.get(identifiers, fields, should_error=should_error)

    @Created.emitted_by
    async def add(self, entity: TEntity) -> TEntity:
        return await self.repository.add(entity)

    @Updated.emitted_by
    async def patch(self, id_: Any, partial: TEntity, **kwargs: Any) -> TEntity | None:
        return await self.repository.patch(id_, partial, **kwargs)

    @Updated.emitted_by
    async def replace(self, id_: Any, entity: TEntity, **kwargs: Any) -> TEntity | None:
        return await self.repository.replace(id_, entity, **kwargs)

    @Deleted.emitted_by
    async def delete(self, entity: TEntity | str | int, **kwargs: Any) -> None:
        await self.repository.delete(entity, **kwargs)

    async def bulk_create(self, bulk: list[TEntity]) -> BulkResponseModel:
        return await self.repository.bulk_create(bulk)

    async def bulk_update(self, bulk: list[TEntity]) -> list:
        return await self.repository.bulk_update(bulk)

    async def bulk_delete(self, bulk: list[TEntity | Any]) -> list:
        return await self.repository.bulk_delete(bulk)
