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
from typing import TYPE_CHECKING, Any, Generic, TypeVar, get_args, get_origin

from pydantic import BaseModel

from furiousapi.service.events import (
    Created,
    Deleted,
    EventsDict,
    ModelEventsDict,
    RegistryEntry,
    Updated,
    collect_handlers,
    install_events,
    install_wrappers,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from enum import Enum

    from furiousapi.api.responses import BulkResponseModel
    from furiousapi.db.repository import BaseRepository


# Bound to BaseModel to match BaseRepository[T: BaseModel] — entities are
# pydantic models throughout the framework.
TEntity = TypeVar("TEntity", bound=BaseModel)


def _extract_model(namespace: dict[str, Any]) -> type | None:
    """Resolve the entity model for a service class (design: hybrid).

    1. An explicit ``__model__`` in the class body always wins.
    2. Otherwise scan **all** of ``__orig_bases__`` (not just the first — a
       service may list mixins before ``ModelService[X]``) for a parametrized
       ``ModelService`` base and lift its concrete argument.

    Returns ``None`` when no concrete model can be determined — e.g. the class is
    still generic (the arg is a ``TypeVar``) or the arg is a forward ref / string
    (not a real ``type``). Callers decide whether that ``None`` is an error
    (see :func:`_requires_model`).
    """
    explicit = namespace.get("__model__")
    if explicit is not None:
        return explicit
    model_base = globals().get("ModelService")
    if model_base is None:  # bootstrap: ModelService not defined yet
        return None
    for orig in namespace.get("__orig_bases__", ()):
        origin = get_origin(orig)
        if isinstance(origin, type) and issubclass(origin, model_base):
            args = get_args(orig)
            # A real class (not a TypeVar — still generic — nor a forward ref).
            if args and isinstance(args[0], type):
                return args[0]
    return None


def _requires_model(cls: type) -> bool:
    """True if ``cls`` is a *concrete* ``ModelService`` subclass that must have
    resolved a model. Abstract roots, ``ModelService`` itself, and still-generic
    services (with free type parameters) are exempt."""
    model_base = globals().get("ModelService")
    if model_base is None or cls is model_base or not issubclass(cls, model_base):
        return False
    if getattr(cls, "__model__", None) is not None:
        return False  # resolved its own, or inherited a parent's model
    return not getattr(cls, "__parameters__", ())  # free TypeVars ⇒ still generic


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
        model = _extract_model(namespace)
        if model is not None:
            namespace = {"__model__": model, **namespace}
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if model is None and _requires_model(cls):
            raise TypeError(
                f"{name} is a concrete ModelService subclass but its entity model could "
                f"not be determined. Parametrize it (class {name}(ModelService[YourEntity])) "
                f"or set `__model__ = YourEntity` explicitly in the class body."
            )
        # Merge events across the MRO (services + mixins) and, when the model is
        # known, rebind to per-service identity (Created → Created[Order]).
        install_events(cls, model)
        cls._event_handlers = collect_handlers(cls)
        install_wrappers(cls)
        return cls


class BaseService(metaclass=ServiceMeta):
    """Abstract root of the service hierarchy."""

    # Annotation only (no default): a bare BaseService has no events until a
    # subclass declares them. Gives BaseService subclasses (non-ModelService,
    # e.g. an infrastructure service with only custom events) a typed `events`
    # namespace. `ModelService` narrows this to `ModelEventsDict[TEntity]` and
    # seeds the CRUD defaults.
    events: EventsDict[Any]


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
