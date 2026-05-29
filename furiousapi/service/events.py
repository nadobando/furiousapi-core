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
import logging
import warnings
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Protocol, TypeVar, cast, overload

# `ExceptionGroup` is the `on_hook_error` payload (annotated here, constructed by
# `_run_on_hook_error`). The `exceptiongroup` package re-exports the builtin on
# 3.11+ and provides the backport on 3.10, so this import is correct everywhere.
from exceptiongroup import ExceptionGroup
from pydantic import BaseModel, ConfigDict, Field
from pydantic._internal._model_construction import ModelMetaclass

logger = logging.getLogger(__name__)

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


class MultipleHookErrorSinksWarning(UserWarning):
    """A class body declares >1 ``on_hook_error`` sink for the same event.

    The sink is singular (unlike ``before``/``after``/``on_error``, which stack).
    Inherited sinks are fine — that's how a service layers on top of the
    framework; this warns only about duplicates written in one class body.
    """


# ──────────────────────────────────────────────────────────────────────────
# Per-phase handler Protocols. Params are positional-only — the framework calls
# handlers positionally, so names need not match. Handlers return ``None`` (they
# observe/validate; they don't produce a value). These constrain the *shape* of
# the decorated function; mypy enforces arity + the known 2nd-arg type. The
# event entity type and ``after``'s result type stay ``Any`` from the decorator
# side (the developer annotates ``event: Created[Order]`` / ``result: Order``).
# ──────────────────────────────────────────────────────────────────────────
class BeforeHandler(Protocol):
    def __call__(self, _s: Any, event: Any, /) -> Awaitable[None]: ...


class AfterHandler(Protocol):
    def __call__(self, _s: Any, event: Any, result: Any, /) -> Awaitable[None]: ...


class OnErrorHandler(Protocol):
    def __call__(self, _s: Any, event: Any, exc: Exception, /) -> Awaitable[None]: ...


class OnHookErrorHandler(Protocol):
    def __call__(self, _s: Any, event: Any, errors: ExceptionGroup, /) -> Awaitable[None]: ...


# Per-phase decorator Protocols: what ``Event.before`` / ``.after`` / ... return.
# Each is overloaded for both call forms and constrains the handler to its phase::
#
#     @Created.after                          # bare:       (handler) -> handler
#     @Created.after(skips=True, priority=10) # parametric: (...) -> (handler) -> handler
_BeforeH = TypeVar("_BeforeH", bound=BeforeHandler)
_AfterH = TypeVar("_AfterH", bound=AfterHandler)
_OnErrorH = TypeVar("_OnErrorH", bound=OnErrorHandler)
_OnHookErrorH = TypeVar("_OnHookErrorH", bound=OnHookErrorHandler)


class BeforeDecorator(Protocol):
    # `raises=True` (default) → a failing precondition raises (aborts the operation).
    @overload
    def __call__(self, handler: _BeforeH, /) -> _BeforeH: ...
    @overload
    def __call__(self, *, raises: bool = ..., priority: int = ...) -> Callable[[_BeforeH], _BeforeH]: ...


class AfterDecorator(Protocol):
    # `skips=True` → a failing after-handler skips the remaining after-handlers.
    @overload
    def __call__(self, handler: _AfterH, /) -> _AfterH: ...
    @overload
    def __call__(self, *, skips: bool = ..., priority: int = ...) -> Callable[[_AfterH], _AfterH]: ...


class OnErrorDecorator(Protocol):
    # `skips=True` → a failing on_error handler skips the remaining on_error handlers.
    @overload
    def __call__(self, handler: _OnErrorH, /) -> _OnErrorH: ...
    @overload
    def __call__(self, *, skips: bool = ..., priority: int = ...) -> Callable[[_OnErrorH], _OnErrorH]: ...


class OnHookErrorDecorator(Protocol):
    # Bare-only — no chain flag (a singular sink has no chain to stop) and no
    # `priority` (nothing to order). See `MultipleHookErrorSinksWarning`.
    def __call__(self, handler: _OnHookErrorH, /) -> _OnHookErrorH: ...


class ContextManagerHandler(Protocol):
    # A structural wrapping hook — an async generator whose single ``yield`` is
    # the method seam. Returns an async iterator, NOT ``None`` (distinguishes it
    # from the boundary hooks).
    def __call__(self, _s: Any, event: Any, /) -> AsyncIterator[Any]: ...


_CmH = TypeVar("_CmH", bound=ContextManagerHandler)


class ContextManagerDecorator(Protocol):
    # Nests by ``priority`` (lower = outermost); no chain flag (a pre-``yield``
    # raise always aborts) and no result control — see design.md §12.
    @overload
    def __call__(self, handler: _CmH, /) -> _CmH: ...
    @overload
    def __call__(self, *, priority: int = ...) -> Callable[[_CmH], _CmH]: ...


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

    # `breaks` is the single internal mechanism ("a raise stops this chain").
    # Decorators expose it under phase-appropriate public names: `raises` on
    # `before`, `skips` on `after`/`on_error`.
    __slots__ = ("breaks", "event_cls", "phase", "priority")

    def __init__(
        self,
        event_cls: type[BaseEvent],
        phase: str,
        *,
        breaks: bool,
        priority: int,
    ) -> None:
        self.event_cls = event_cls
        self.phase = phase
        self.breaks = breaks
        self.priority = priority

    def __repr__(self) -> str:
        return f"HandlerSpec({self.event_cls.__name__}.{self.phase}, breaks={self.breaks}, priority={self.priority})"


def _tag_handler(handler: F, spec: HandlerSpec) -> F:
    specs = getattr(handler, HANDLERS_ATTR, None)
    if specs is None:
        specs = []
        setattr(handler, HANDLERS_ATTR, specs)
    specs.append(spec)
    return handler


def _make_handler_decorator(
    event_cls: type[BaseEvent], phase: str, *, default_breaks: bool, flag_name: str | None = None
) -> Callable[..., Any]:
    """Build the decorator returned by a hook property.

    ``flag_name`` is the public kwarg that maps to the internal ``breaks`` field
    — ``"raises"`` for ``before``, ``"skips"`` for ``after``/``on_error``, or
    ``None`` (no chain flag) for ``on_hook_error``/``contextmanager``. Supports::

        @Created.after                          # bare; phase defaults
        @Created.after(skips=True, priority=10)  # parametric
    """

    def decorator(*args: Any, **kwargs: Any) -> Any:
        # Bare form: the single positional arg is the handler.
        if len(args) == 1 and not kwargs and callable(args[0]):
            spec = HandlerSpec(event_cls, phase, breaks=default_breaks, priority=DEFAULT_PRIORITY)
            return _tag_handler(args[0], spec)

        # Parametric form: keyword args only.
        if args:
            raise TypeError(
                f"{event_cls.__name__}.{phase} takes only keyword arguments "
                f"in its parametric form; got positional {args!r}"
            )
        breaks = kwargs.pop(flag_name, default_breaks) if flag_name else default_breaks
        priority = kwargs.pop("priority", DEFAULT_PRIORITY)
        if kwargs:
            raise TypeError(f"{event_cls.__name__}.{phase} got unexpected keyword arguments: {sorted(kwargs)!r}")

        def inner(handler: F) -> F:
            return _tag_handler(handler, HandlerSpec(event_cls, phase, breaks=breaks, priority=priority))

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
    def before(cls) -> BeforeDecorator:  # noqa: N805  (cls is correct for a metaclass)
        """Register a handler that runs before the wrapped method. ``raises=True``
        (default) — a failing precondition raises (skips the method, propagates
        bare); ``raises=False`` — observed, the method still runs."""
        deco = _make_handler_decorator(cast("type[BaseEvent]", cls), "before", default_breaks=True, flag_name="raises")
        return cast("BeforeDecorator", deco)

    @property
    def after(cls) -> AfterDecorator:  # noqa: N805  (cls is correct for a metaclass)
        """Register a handler that runs after the method succeeds. ``skips=True``
        stops the remaining after-handlers (never propagates — the method already
        succeeded); ``skips=False`` (default) runs them all, collecting failures."""
        deco = _make_handler_decorator(cast("type[BaseEvent]", cls), "after", default_breaks=False, flag_name="skips")
        return cast("AfterDecorator", deco)

    @property
    def on_error(cls) -> OnErrorDecorator:  # noqa: N805  (cls is correct for a metaclass)
        """Register an OBSERVER that runs if the method raised. The method's
        exception always propagates bare regardless; ``skips=True`` only stops the
        remaining on_error handlers; ``skips=False`` (default) runs them all."""
        deco = _make_handler_decorator(
            cast("type[BaseEvent]", cls), "on_error", default_breaks=False, flag_name="skips"
        )
        return cast("OnErrorDecorator", deco)

    @property
    def on_hook_error(cls) -> OnHookErrorDecorator:  # noqa: N805  (cls is correct for a metaclass)
        """Register the terminal OBSERVER sink. Receives all collected
        before/after/on_error handler failures as one ``ExceptionGroup``.
        Observe-only — cannot change the caller's outcome; if it raises, that is
        logged and not re-dispatched (recursion guard). See design.md §6."""
        deco = _make_handler_decorator(cast("type[BaseEvent]", cls), "on_hook_error", default_breaks=False)
        return cast("OnHookErrorDecorator", deco)

    @property
    def contextmanager(cls) -> ContextManagerDecorator:  # noqa: N805  (cls is correct for a metaclass)
        """Register a STRUCTURAL wrapping hook — an async generator whose single
        ``yield`` is the method seam. Cms nest by ``priority`` (lower = outermost)
        and unwind LIFO, like ``async with`` / middleware. Full control: a pre-
        ``yield`` raise aborts; the method's exception is thrown in and may be
        re-raised or mapped. See design.md §12."""
        deco = _make_handler_decorator(cast("type[BaseEvent]", cls), "contextmanager", default_breaks=False)
        return cast("ContextManagerDecorator", deco)


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
        before: ClassVar[BeforeDecorator]
        after: ClassVar[AfterDecorator]
        on_error: ClassVar[OnErrorDecorator]
        on_hook_error: ClassVar[OnHookErrorDecorator]
        contextmanager: ClassVar[ContextManagerDecorator]

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


class BaseServiceMixin:
    """Marker base for service mixins.

    A **plain class** — it carries none of ``ServiceMeta``'s machinery (no model
    extraction, no event rebinding, no wrapper install). A mixin only
    *contributes* handlers (and optionally an ``events`` namespace) to the
    service that mixes it in; it is never instantiated as a service itself.
    ``_is_contributor`` recognises it via ``issubclass`` when walking the MRO to
    collect handlers and events.

    Lives in ``events.py`` (alongside the collection machinery that keys on it)
    rather than in ``base.py`` so the contract is co-located with its consumer.
    ``base.py`` re-exports it for the public import path.
    """


def _is_contributor(klass: type, cls: type) -> bool:
    """Whether ``klass`` contributes handlers/events to ``cls`` — the class being
    built, a service class (carries its own ``_event_handlers``), or a
    ``BaseServiceMixin`` subclass. Plain bases like ``object``/``Generic`` are
    skipped."""
    return klass is cls or issubclass(klass, BaseServiceMixin) or "_event_handlers" in vars(klass)


def collect_handlers(cls: type) -> dict[tuple[type, str], list[RegistryEntry]]:
    """Build the handler registry by walking ``cls.__mro__`` and scanning each
    contributor's own namespace for tagged handlers.

    Walking the MRO (base → derived) means mixin chains and diamonds collect
    without double-counting — each class appears exactly once. Entries are NOT
    sorted here; sorting by (priority, index) happens at dispatch time.

    Registry shape: ``{(event_cls, phase): [RegistryEntry, ...]}``.
    """
    registry: dict[tuple[type, str], list[RegistryEntry]] = {}
    own_sinks: dict[type, list[str]] = {}  # event_cls -> on_hook_error methods in cls's OWN body
    index = 0

    for klass in reversed(cls.__mro__):  # base → derived: ties break with ancestors first
        if not _is_contributor(klass, cls):
            continue
        for method_name, value in vars(klass).items():
            for spec in getattr(value, HANDLERS_ATTR, ()):
                registry.setdefault((spec.event_cls, spec.phase), []).append(RegistryEntry(method_name, spec, index))
                index += 1
                if spec.phase == "on_hook_error" and klass is cls:
                    own_sinks.setdefault(spec.event_cls, []).append(method_name)

    _warn_on_duplicate_sinks(own_sinks, cls.__qualname__)
    return registry


def _warn_on_duplicate_sinks(own_sinks: dict[type, list[str]], cls_name: str) -> None:
    """Warn if a class body declares >1 ``on_hook_error`` sink for one event.

    The sink is singular per event; stacking it is almost always a
    misunderstanding (it doesn't compose like the other hooks). Inherited sinks
    are intentional layering and are deliberately not counted (own body only).
    """
    for event_cls, methods in own_sinks.items():
        if len(methods) > 1:
            warnings.warn(
                f"{cls_name} declares {len(methods)} on_hook_error sinks for "
                f"{event_cls.__name__} ({', '.join(methods)}) — they all fire for one "
                f"dispatch. on_hook_error is a single sink (unlike before/after/on_error); "
                f"consolidate into one.",
                MultipleHookErrorSinksWarning,
                stacklevel=2,
            )


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


def _sorted_entries(instance: Any, event_cls: type[BaseEvent], phase: str) -> list[RegistryEntry]:
    """Handlers for ``(event_cls, phase)``, gathered across the event's MRO and
    sorted by ``(priority, registration_index)`` — lower priority first.

    .. warning::
        **Handlers fire for the event class AND every ancestor in its MRO.**
        This is what makes cross-cutting handlers possible — a handler decorated
        ``@BaseEvent.after`` (or ``@MyDomainEvent.after``) fires for *every*
        descendant event the service dispatches. Concretely:

        * ``@Created.after`` fires for ``Created`` AND ``Created[Order]``,
          ``Created[User]``, etc. — desirable.
        * ``@BaseEvent.after`` fires for **every event the service ever
          dispatches** — ``Created``, ``Updated``, ``Deleted``, and any custom
          events. Useful for telemetry / audit / correlation-id propagation;
          dangerous for anything domain-specific.

        Treat ``BaseEvent``-level (and any other broadly-shared ancestor)
        registrations as **wildcard** registrations. Register them only for
        truly cross-cutting concerns. If you need "fire for any *Created*
        variant," use ``Created`` — not ``BaseEvent``.

        Aggregation walks ``event_cls.__mro__`` once per dispatch; duplicates
        are not possible because each handler is registered against one
        ``(event_cls, phase)`` key in the registry. Ordering across MRO levels
        is by ``(priority, registration_index)`` — there is *no* implicit
        "base handlers run first" rule; if you need that, use ``priority``.
    """
    registry = type(instance)._event_handlers  # noqa: SLF001  (framework-internal registry)
    entries: list[RegistryEntry] = []
    for ancestor in event_cls.__mro__:
        entries.extend(registry.get((ancestor, phase), ()))
    entries.sort(key=lambda e: (e.spec.priority, e.index))
    return entries


async def _run_phase(
    instance: Any,
    event_cls: type[BaseEvent],
    phase: str,
    event: BaseEvent,
    extra: Any = None,
    *,
    has_extra: bool,
    collected: list[Exception],
) -> Exception | None:
    """Run all handlers for ``phase`` in order, appending any failure to the
    shared ``collected`` bucket. Stops at the first ``breaks=True`` failure and
    returns it — the caller decides what that means. For ``before`` it propagates
    (``raises``); ``after``/``on_error`` ignore the return, so their ``breaks``
    (``skips``) just stops the chain. See design.md §6."""
    breaking: Exception | None = None
    for entry in _sorted_entries(instance, event_cls, phase):
        handler = getattr(instance, entry.method_name)
        try:
            if has_extra:
                await handler(event, extra)
            else:
                await handler(event)
        except Exception as exc:  # noqa: BLE001  (collected, surfaced via raises / on_hook_error)
            collected.append(exc)
            if entry.spec.breaks:
                breaking = exc
                break
    return breaking


async def _run_on_hook_error(
    instance: Any, event_cls: type[BaseEvent], event: BaseEvent, collected: list[Exception]
) -> None:
    """Terminal observer sink. No-op on an empty bucket; otherwise hands every
    collected handler failure to the ``on_hook_error`` sink(s) as one
    ``ExceptionGroup``. Observe-only and recursion-guarded: a sink that raises is
    logged and NOT re-dispatched, and never changes the caller's outcome."""
    if not collected:
        return
    group = ExceptionGroup("handler failures during event dispatch", collected)
    for entry in _sorted_entries(instance, event_cls, "on_hook_error"):
        handler = getattr(instance, entry.method_name)
        try:
            await handler(event, group)
        except Exception:  # noqa: BLE001  (observe-only: log, never re-dispatch to on_hook_error)
            logger.exception(
                "on_hook_error sink %s.%s raised; suppressed (recursion guard)",
                type(instance).__name__,
                entry.method_name,
            )


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


_UNSET = object()  # sentinel: distinguishes "no result yet" from a real None/falsy result


async def _run_boundary(
    instance: Any,
    event_cls: type[BaseEvent],
    event: BaseEvent,
    method: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """The boundary-tier lifecycle around the method: before → method →
    on_error/after → on_hook_error (design.md §6). Caller path is always bare —
    only a ``before`` ``raises=True`` failure or the method's own exception
    reaches the caller; all handler failures funnel to ``on_hook_error``."""
    collected: list[Exception] = []

    # BEFORE — raises=True ⇒ skip the method, propagate bare.
    raised = await _run_phase(instance, event_cls, "before", event, has_extra=False, collected=collected)
    if raised is not None:
        await _run_on_hook_error(instance, event_cls, event, collected)
        raise raised

    # METHOD — sacred: its own exception always propagates bare, never grouped.
    try:
        result = await method(instance, *args, **kwargs)
    except Exception as method_exc:
        await _run_phase(instance, event_cls, "on_error", event, method_exc, has_extra=True, collected=collected)
        await _run_on_hook_error(instance, event_cls, event, collected)
        raise

    # AFTER — skips=True ⇒ stop the rest; after failures never propagate.
    await _run_phase(instance, event_cls, "after", event, result, has_extra=True, collected=collected)
    await _run_on_hook_error(instance, event_cls, event, collected)
    return result


async def _run_with_contextmanagers(
    instance: Any,
    event_cls: type[BaseEvent],
    event: BaseEvent,
    method: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    cm_entries: list[RegistryEntry],
) -> Any:
    """Wrap the boundary lifecycle in the structural ``.contextmanager`` stack.

    Cms enter in priority order (lower = outermost) and unwind LIFO — exactly an
    ``AsyncExitStack`` of ``asynccontextmanager``-adapted generators. A pre-yield
    raise aborts; the boundary's exception is thrown into the cms (they may map
    it); a cm that *suppresses* the exception without a result is a usage error."""
    result: Any = _UNSET
    async with AsyncExitStack() as stack:
        for entry in cm_entries:  # ascending priority = outermost entered first
            factory = asynccontextmanager(getattr(instance, entry.method_name))
            await stack.enter_async_context(factory(event))
        result = await _run_boundary(instance, event_cls, event, method, args, kwargs)
    if result is _UNSET:
        raise RuntimeError(
            "a .contextmanager suppressed the operation's exception without providing a result; "
            "re-raise or map it instead (result-replacement is not supported)"
        )
    return result


def _make_wrapper(method: Callable[..., Any], event_cls: type[BaseEvent]) -> Callable[..., Any]:
    """Wrap a CRUD/custom method with the event lifecycle (design.md §6/§9/§12).

    Structural ``.contextmanager`` hooks (if any) wrap the boundary-tier
    lifecycle; otherwise the boundary runs directly.
    """
    signature = inspect.signature(method)

    @functools.wraps(method)
    async def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        resolved = _resolve_event(self, event_cls)
        event = _build_event(resolved, signature, self, args, kwargs)
        cm_entries = _sorted_entries(self, resolved, "contextmanager")
        if not cm_entries:
            return await _run_boundary(self, resolved, event, method, args, kwargs)
        return await _run_with_contextmanagers(self, resolved, event, method, args, kwargs, cm_entries)

    setattr(wrapped, WRAPPED_ATTR, True)
    return wrapped


def collect_events(cls: type) -> EventsDict:
    """Merge the ``events`` declared across ``cls.__mro__`` into one namespace.

    Walks base → derived and unions each contributing class's *own* ``events``
    (read from its ``__dict__``, so inherited copies aren't double-counted); a
    derived class's entry wins on a name collision. This is what lets an
    intermediate/leaf service — or a mixin — *add* events rather than shadow the
    ones it inherited.
    """
    merged: EventsDict = EventsDict()
    for klass in reversed(cls.__mro__):
        if not _is_contributor(klass, cls):
            continue
        own = vars(klass).get("events")
        if isinstance(own, EventsDict):
            merged.update(own)
    return merged


def _parametrize_events(events: EventsDict, model: type) -> EventsDict:
    """Turn still-generic events (``Created``) into per-service bound versions
    (``Created[Order]``); leave already-bound / non-generic events as-is."""
    rebound: EventsDict = EventsDict()
    for name, event_cls in events.items():
        meta = getattr(event_cls, "__pydantic_generic_metadata__", None)
        rebound[name] = event_cls[model] if meta and meta.get("parameters") else event_cls
    return rebound


def install_events(cls: type, model: type | None) -> None:
    """Merge the events contributed across the MRO and (when the entity model is
    known) parametrize them, installing the result as ``cls.events``. Runs for
    every service so mixins / feature bases / leaf services all compose."""
    merged = collect_events(cls)
    if not merged:
        return
    if model is not None:
        merged = _parametrize_events(merged, model)
    setattr(cls, "events", merged)  # noqa: B010  (cls.events not statically known on `type`)


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
