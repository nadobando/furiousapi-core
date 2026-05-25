"""Event class machinery (step 2 — bare minimum).

* :class:`EventMeta` — pydantic-compatible metaclass that captures the
  ``wraps=`` class kwarg (PEP 487 style) into ``cls.__wraps_methods__``.
* :class:`BaseEvent` — pydantic frozen ``BaseModel`` with a built-in mutable
  ``metadata`` dict.

Wire an event to a method via ``wraps=``::

    class Created(BaseEvent, wraps="add"):
        entity: Order

    class Updated(BaseEvent, wraps=("patch", "replace")):
        id_: Any
        entity: Order

The class kwarg is stored as a tuple of method names on
``cls.__wraps_methods__``; ``ServiceMeta`` reads this later to know which
methods to wrap. No wrapping happens at this layer.

Triple-duty ``__call__`` (decorator path), handler decorators
(``.before``/``.after``/``.on_error``), generic ``TResult``, and type-checker
overloads land in subsequent steps.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Protocol, TypeVar, cast, overload

from pydantic import BaseModel, ConfigDict, Field
from pydantic._internal._model_construction import ModelMetaclass

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


class HandlerDecorator(Protocol):
    """The callable returned by ``Event.before`` / ``.after`` / ``.on_error``.

    Overloaded so both forms type-check::

        @Created.after                          # bare: (handler) -> handler
        @Created.after(abort=True, priority=10) # parametric: (...) -> (handler) -> handler
    """

    @overload
    def __call__(self, handler: F, /) -> F: ...
    @overload
    def __call__(self, *, abort: bool = ..., priority: int = ...) -> Callable[[F], F]: ...


class EmitterDecorator(Protocol):
    """The callable returned by ``Event.emitted_by`` — marks a method as
    emitting the event. Identity-preserving: ``(F) -> F``."""

    def __call__(self, func: F, /) -> F: ...


# Default handler priority (lower fires first). Lives here for now; moves to a
# config module later.
DEFAULT_PRIORITY = 50

# Attribute on a handler function holding its list of HandlerSpecs. A list
# because one method can be decorated multiple times (e.g. @A.after @B.after).
HANDLERS_ATTR = "__furious_handlers__"

# Marker on a method that's already been wrapped with the firing lifecycle.
WRAPPED_ATTR = "__furious_wrapped__"

# Attribute on a method holding the tuple of event classes it emits, set by the
# `@Event` decorator (the supplementary emitter — visible at the method site,
# additive with each event's own `wraps=`).
EMITS_ATTR = "__furious_emits__"


class HandlerSpec:
    """One handler registration: which event, which phase, and how it behaves."""

    __slots__ = ("abort", "event_cls", "phase", "priority")

    def __init__(
        self,
        event_cls: type[BaseEvent],
        phase: str,
        *,
        abort: bool,
        priority: int,
    ) -> None:
        self.event_cls = event_cls
        self.phase = phase
        self.abort = abort
        self.priority = priority

    def __repr__(self) -> str:
        return f"HandlerSpec({self.event_cls.__name__}.{self.phase}, abort={self.abort}, priority={self.priority})"


def _tag_handler(handler: F, spec: HandlerSpec) -> F:
    specs = getattr(handler, HANDLERS_ATTR, None)
    if specs is None:
        specs = []
        setattr(handler, HANDLERS_ATTR, specs)
    specs.append(spec)
    return handler


def _make_handler_decorator(event_cls: type[BaseEvent], phase: str, *, default_abort: bool) -> HandlerDecorator:
    """Build the decorator returned by ``Event.before`` / ``.after`` / ``.on_error``.

    Supports both forms::

        @Created.after                         # bare; phase defaults
        @Created.after(abort=True, priority=10) # parametric
    """

    def decorator(*args: Any, **kwargs: Any) -> Any:
        # Bare form: the single positional arg is the handler.
        if len(args) == 1 and not kwargs and callable(args[0]):
            spec = HandlerSpec(event_cls, phase, abort=default_abort, priority=DEFAULT_PRIORITY)
            return _tag_handler(args[0], spec)

        # Parametric form: keyword args only.
        if args:
            raise TypeError(
                f"{event_cls.__name__}.{phase} takes only keyword arguments "
                f"in its parametric form; got positional {args!r}"
            )
        abort = kwargs.pop("abort", default_abort)
        priority = kwargs.pop("priority", DEFAULT_PRIORITY)
        if kwargs:
            raise TypeError(f"{event_cls.__name__}.{phase} got unexpected keyword arguments: {sorted(kwargs)!r}")

        def inner(handler: F) -> F:
            return _tag_handler(handler, HandlerSpec(event_cls, phase, abort=abort, priority=priority))

        return inner

    return decorator


class EventMeta(ModelMetaclass):
    """Capture the ``wraps=`` class kwarg into ``cls.__wraps_methods__``, and
    expose the ``.emitted_by`` emitter decorator + ``.before`` / ``.after`` /
    ``.on_error`` handler decorators.

    All four are properties on the METACLASS (not on ``BaseEvent``) because
    they're accessed as class attributes (``SomeEvent.after``) — a class is an
    instance of its metaclass, so a property here fires for that access. A
    property on ``BaseEvent`` would only fire for instance access
    (``event_instance.after``), which is not what we want.

    Routing the emitter through a property (``Event.emitted_by``) rather than
    through ``__call__`` is deliberate: ``__call__`` is owned by pydantic's
    mypy plugin (for construction), so a ``@SomeEvent`` decorator can't be
    typed. ``@SomeEvent.emitted_by`` goes through a property returning a typed
    identity decorator, so it preserves the method's signature.
    """

    # Per-event-class attribute (each EventMeta instance — i.e. each event class
    # — has its own). NOT a ClassVar: that would forbid assigning it via `cls`.
    __wraps_methods__: tuple[str, ...]

    def __new__(  # noqa: PYI034  (metaclass __new__ returns the metaclass, not Self)
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        *,
        wraps: str | tuple[str, ...] | None = None,
        **kwargs: Any,
    ) -> EventMeta:
        wraps_tuple = _resolve_wraps(wraps, bases)
        # super().__new__ is typed as returning `type`; at runtime it's an
        # EventMeta instance. Cast so attribute set + return type check out.
        cls = cast("EventMeta", super().__new__(mcs, name, bases, namespace, **kwargs))
        cls.__wraps_methods__ = wraps_tuple
        return cls

    @property
    def emitted_by(cls) -> EmitterDecorator:  # noqa: N805  (cls is correct for a metaclass)
        """Mark a method as emitting this event. Identity-preserving (keeps the
        method's signature, so call sites stay typed). Additive with the event's
        own ``wraps=`` — both wire the method, deduped by ``install_wrappers``."""
        event_cls = cast("type[BaseEvent]", cls)

        def deco(func: F) -> F:
            existing: tuple[type, ...] = getattr(func, EMITS_ATTR, ())
            func.__furious_emits__ = (*existing, event_cls)  # type: ignore[attr-defined]
            return func

        return deco

    @property
    def before(cls) -> HandlerDecorator:  # noqa: N805  (cls is correct for a metaclass)
        """Register a handler that runs before the wrapped method. Default
        ``abort=True`` (a raising before-handler aborts the operation)."""
        return _make_handler_decorator(cast("type[BaseEvent]", cls), "before", default_abort=True)

    @property
    def after(cls) -> HandlerDecorator:  # noqa: N805  (cls is correct for a metaclass)
        """Register a handler that runs after the method succeeds. Default
        ``abort=False`` (a raising after-handler is collected, not fatal)."""
        return _make_handler_decorator(cast("type[BaseEvent]", cls), "after", default_abort=False)

    @property
    def on_error(cls) -> HandlerDecorator:  # noqa: N805  (cls is correct for a metaclass)
        """Register a handler that runs if the method raised. Default
        ``abort=False``."""
        return _make_handler_decorator(cast("type[BaseEvent]", cls), "on_error", default_abort=False)


def _resolve_wraps(wraps: str | tuple[str, ...] | None, bases: tuple[type, ...]) -> tuple[str, ...]:
    if wraps is None:
        # Inherit from the first parent that has a non-empty value.
        for base in bases:
            inherited = getattr(base, "__wraps_methods__", ())
            if inherited:
                return inherited
        return ()
    if isinstance(wraps, str):
        return (wraps,)
    return tuple(wraps)


class BaseEvent(BaseModel, metaclass=EventMeta):
    """Base for all events.

    Frozen by default (events are facts that happened; facts don't mutate).
    The ``metadata`` dict's *contents* are mutable even on a frozen model —
    use it for cross-cutting accumulation (correlation_id, span_id, etc.)
    without breaking the immutability contract.
    """

    if TYPE_CHECKING:
        # Type-checker-only stubs. At runtime these come from EventMeta's
        # properties; declared here so IDEs (which don't reliably resolve
        # metaclass properties as class attributes) see `SomeEvent.after` etc.
        emitted_by: ClassVar[EmitterDecorator]
        before: ClassVar[HandlerDecorator]
        after: ClassVar[HandlerDecorator]
        on_error: ClassVar[HandlerDecorator]

    model_config = ConfigDict(frozen=True)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventsDict(dict, Generic[T]):
    """A dict of event classes with attribute-style access.

    Subclasses declare typed slots as class-level annotations (no values), e.g.::

        class ModelEventsDict(EventsDict[T], Generic[T]):
            Created: type[Created[T]]
            Updated: type[Updated[T]]

    At runtime the slots aren't real attributes (annotation-only), so
    ``events.Created`` falls through to ``__getattr__`` → dict lookup. At
    type-check time, the explicit annotation takes precedence over
    ``__getattr__``, so ``events.Created`` is typed precisely and the generic
    parameter ``T`` propagates (``events.Created(...).entity`` infers ``T``).

    Note: class-level access (``ServiceClass.events.Created``) trips mypy's
    "Access to generic instance variables via class is ambiguous" [misc]
    warning, because the generic param binds per-instance. The reveal_type is
    still correct; the warning is cosmetic. Instance access
    (``self.events.Created``) is warning-free.
    """

    def __getattr__(self, name: str) -> type[BaseEvent]:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


# ──────────────────────────────────────────────────────────────────────────
# Handler registry + firing machinery.
#
# ServiceMeta (in base.py) calls `collect_handlers` and `install_wrappers`;
# everything here is event-infrastructure, independent of the service classes.
# ──────────────────────────────────────────────────────────────────────────


class RegistryEntry:
    """A collected handler: its method name on the service, its spec, and a
    monotonic registration index (tiebreaker when priorities are equal)."""

    __slots__ = ("index", "method_name", "spec")

    def __init__(self, method_name: str, spec: HandlerSpec, index: int) -> None:
        self.method_name = method_name
        self.spec = spec
        self.index = index

    def __repr__(self) -> str:
        return f"RegistryEntry({self.method_name!r}, {self.spec!r}, index={self.index})"


def collect_handlers(bases: tuple[type, ...], namespace: dict[str, Any]) -> dict[tuple[type, str], list[RegistryEntry]]:
    """Build the handler registry for a class: inherit parent registries, then
    append handlers tagged on this class's own methods.

    Entries are NOT sorted here — sorting by (priority, index) happens at
    dispatch time (so wildcard MRO collection and subclass priority overrides
    compose correctly).

    Registry shape: ``{(event_cls, phase): [RegistryEntry, ...]}``.
    """
    registry: dict[tuple[type, str], list[RegistryEntry]] = {}
    next_index = 0

    # Inherit parent registries (left-to-right = MRO declaration order).
    for base in bases:
        parent = getattr(base, "_event_handlers", None)
        if not parent:
            continue
        for key, entries in parent.items():
            registry.setdefault(key, []).extend(entries)
            for entry in entries:
                next_index = max(next_index, entry.index + 1)

    # Own handlers, in class-body definition order.
    for method_name, value in namespace.items():
        specs = getattr(value, HANDLERS_ATTR, None)
        if not specs:
            continue
        for spec in specs:
            key = (spec.event_cls, spec.phase)
            registry.setdefault(key, []).append(RegistryEntry(method_name, spec, next_index))
            next_index += 1

    return registry


def _build_event(
    event_cls: type[BaseEvent],
    signature: inspect.Signature,
    instance: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> BaseEvent:
    """Construct the event from the wrapped method's call args, filtered to the
    event's fields by parameter name."""
    bound = signature.bind(instance, *args, **kwargs)
    bound.apply_defaults()
    arguments = dict(bound.arguments)
    arguments.pop("self", None)
    fields = event_cls.model_fields
    return event_cls(**{k: v for k, v in arguments.items() if k in fields})


async def _fire(
    instance: Any,
    event_cls: type[BaseEvent],
    phase: str,
    event: BaseEvent,
    extra: Any = None,
    *,
    has_extra: bool = False,
) -> None:
    """Run handlers for ``event_cls`` in ``phase``.

    Walks ``event_cls.__mro__`` so a handler registered against a base event
    (e.g. ``@Created.after``, or wildcard ``@BaseEvent.after``) fires for a
    more-specific event (e.g. the per-service ``Created[Order]``). Collected
    handlers run sorted by ``(priority, registration_index)`` — lower priority
    first.

    4c-iii (not yet): abort flag + ExceptionGroup. For now the first handler
    to raise propagates.
    """
    registry = type(instance)._event_handlers  # noqa: SLF001  (framework-internal registry)
    entries: list[RegistryEntry] = []
    for ancestor in event_cls.__mro__:
        entries.extend(registry.get((ancestor, phase), ()))
    entries.sort(key=lambda e: (e.spec.priority, e.index))
    for entry in entries:
        handler = getattr(instance, entry.method_name)
        if has_extra:
            await handler(event, extra)
        else:
            await handler(event)


def _resolve_event(instance: Any, captured: type[BaseEvent]) -> type[BaseEvent]:
    """Resolve the runtime event class for ``instance``.

    The wrapper is installed once (on the class that defines the method) with
    the base event captured. A subclass bound to a concrete entity carries a
    parametrized event in its ``events`` namespace (``Created[Order]``), so at
    call time we look there for an entry that subclasses the captured base.
    Falls back to the captured class if there's no events namespace / match.
    """
    events = getattr(type(instance), "events", None)
    if isinstance(events, EventsDict):
        for candidate in events.values():
            if isinstance(candidate, type) and issubclass(candidate, captured):
                return candidate
    return captured


def _make_wrapper(method: Callable[..., Any], event_cls: type[BaseEvent]) -> Callable[..., Any]:
    """Wrap a CRUD/custom method so it fires the event lifecycle around its body."""
    signature = inspect.signature(method)

    @functools.wraps(method)
    async def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        resolved = _resolve_event(self, event_cls)
        event = _build_event(resolved, signature, self, args, kwargs)
        await _fire(self, resolved, "before", event)
        try:
            result = await method(self, *args, **kwargs)
        except Exception as exc:
            await _fire(self, resolved, "on_error", event, exc, has_extra=True)
            raise
        await _fire(self, resolved, "after", event, result, has_extra=True)
        return result

    setattr(wrapped, WRAPPED_ATTR, True)
    return wrapped


def rebind_events(cls: type, model: type) -> None:
    """Parametrize the class's events with its concrete entity model.

    Turns the shared base events (``Created``, ``Updated``, ...) into
    per-service parametrized versions (``Created[Order]``, ...), giving each
    service distinct event identity + a runtime-bound ``entity`` field. Only
    parametrizes events that are still unbound generics; leaves others as-is.
    Installs a fresh events namespace on ``cls`` so the parent's stays shared.
    """
    events = getattr(cls, "events", None)
    if not isinstance(events, EventsDict):
        return
    rebound = type(events)()
    for name, event_cls in events.items():
        meta = getattr(event_cls, "__pydantic_generic_metadata__", None)
        if meta and meta.get("parameters"):
            rebound[name] = event_cls[model]
        else:
            rebound[name] = event_cls
    setattr(cls, "events", rebound)  # noqa: B010  (cls.events not statically known on `type`)


# ──────────────────────────────────────────────────────────────────────────
# Framework CRUD event shapes (Generic over the entity type) + their typed
# namespace. `wraps=` is a framework-contract binding: every ModelService's
# `add` fires Created, `patch`/`replace` fire Updated, `delete` fires Deleted.
# ──────────────────────────────────────────────────────────────────────────


class Created(BaseEvent, Generic[T], wraps="add"):
    entity: T


class Updated(BaseEvent, Generic[T], wraps=("patch", "replace")):
    # Fields are optional because the two wrapped methods supply different args:
    # replace(id_, entity) fills both; patch(id_, partial) fills only id_ (the
    # `partial` arg doesn't name-match `entity`). The authoritative post-update
    # entity reaches after-handlers via `result`, not via this field.
    # TODO: revisit payload construction for patch (design.md §4 input-vs-output).
    id_: Any = None
    entity: T | None = None


class Deleted(BaseEvent, Generic[T], wraps="delete"):
    entity: T


class ModelEventsDict(EventsDict[T], Generic[T]):
    """Typed event namespace for ``ModelService``. Slots are annotation-only;
    runtime values come from the dict (see ``EventsDict``)."""

    Created: type[Created[T]]
    Updated: type[Updated[T]]
    Deleted: type[Deleted[T]]


def install_wrappers(cls: type) -> None:
    """Find methods wired to events and install a firing wrapper.

    Two wiring sources, collected and deduped per method (first wins):

    1. **Event ``wraps=``** — each event in ``cls.events`` declares which
       method(s) it wraps (``__wraps_methods__``).
    2. **``@Event`` decorator** — a method tagged via the supplementary emitter
       decorator carries ``__furious_emits__``.

    For framework CRUD methods both sources point to the same event (they
    agree), so the dedupe is a no-op; the decorator just makes the wiring
    visible in the source. Idempotent — skips already-wrapped methods so
    inherited wrappers aren't double-wrapped.
    """
    method_to_event: dict[str, type[BaseEvent]] = {}

    # Source 1: event `wraps=` metadata (if the class has an events namespace).
    events = getattr(cls, "events", None)
    if isinstance(events, EventsDict):
        for event_cls in events.values():
            for method_name in getattr(event_cls, "__wraps_methods__", ()):
                method_to_event.setdefault(method_name, event_cls)

    # Source 2: methods tagged with the `@Event` decorator (walk MRO so
    # inherited decorations are found).
    for klass in cls.__mro__:
        for attr_name, attr in vars(klass).items():
            for event_cls in getattr(attr, EMITS_ATTR, ()):
                method_to_event.setdefault(attr_name, event_cls)

    for method_name, event_cls in method_to_event.items():
        method = getattr(cls, method_name, None)
        if method is None or getattr(method, WRAPPED_ATTR, False):
            continue
        setattr(cls, method_name, _make_wrapper(method, event_cls))
