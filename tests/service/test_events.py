"""Runtime behavior tests for the service-layer event system.

Covers: CRUD event firing, the three phases (before/after/on_error), handler
args, priority ordering, wildcard dispatch, custom events, per-service event
identity, handler isolation, and inheritance.

Unused handler args are ``_``-prefixed (the framework calls handlers
positionally, so the name doesn't matter for dispatch — the prefix just signals
"intentionally unused").
"""

from __future__ import annotations

import contextlib
import warnings
from collections.abc import AsyncIterator
from typing import Any, Generic, TypeVar

import pytest
from exceptiongroup import ExceptionGroup
from pydantic import BaseModel, ValidationError

from furiousapi.service import (
    BaseEvent,
    BaseService,
    BaseServiceMixin,
    Created,
    Deleted,
    EventsDict,
    ModelEventsDict,
    ModelService,
    MultipleHookErrorSinksWarning,
    Updated,
)


class Order(BaseModel):
    id: int
    name: str = "x"


class Product(BaseModel):
    sku: str


class FakeRepo:
    """Repository stub — echoes inputs. Only the methods the tests exercise."""

    async def add(self, entity: Any) -> Any:
        return entity

    async def patch(self, _id: Any, partial: Any, **_kwargs: Any) -> Any:
        return partial

    async def replace(self, _id: Any, entity: Any, **_kwargs: Any) -> Any:
        return entity

    async def delete(self, _entity: Any, **_kwargs: Any) -> None:
        return None


S = TypeVar("S", bound=ModelService)


def make_service(service_cls: type[S]) -> S:
    """Construct a service with a fresh log list attached."""
    svc = service_cls(repository=FakeRepo())  # type: ignore[arg-type]
    svc.log = []  # type: ignore[attr-defined]
    return svc


# ─────────────────────────────────────────────────────────────────────────
# CRUD events fire on the matching methods.
# ─────────────────────────────────────────────────────────────────────────


class CrudService(ModelService[Order]):
    log: list

    @Created.after
    async def on_created(self, event: Created[Order], _result: object) -> None:
        self.log.append(("created", event.entity.id))

    @Updated.after
    async def on_updated(self, event: Updated[Order], _result: object) -> None:
        self.log.append(("updated", event.id_))

    @Deleted.after
    async def on_deleted(self, event: Deleted[Order], _result: object) -> None:
        self.log.append(("deleted", event.entity.id))


async def test_add_fires_created():
    s = make_service(CrudService)
    await s.add(Order(id=1))
    assert s.log == [("created", 1)]


async def test_patch_and_replace_fire_updated():
    s = make_service(CrudService)
    await s.patch(7, Order(id=7))
    await s.replace(9, Order(id=9))
    assert s.log == [("updated", 7), ("updated", 9)]


async def test_delete_fires_deleted():
    s = make_service(CrudService)
    await s.delete(Order(id=5))
    assert s.log == [("deleted", 5)]


# ─────────────────────────────────────────────────────────────────────────
# Phases: before runs before the body, after runs after with result,
# on_error runs on failure with the exception (and re-raises).
# ─────────────────────────────────────────────────────────────────────────


class PhaseService(ModelService[Order]):
    log: list

    @Created.before
    async def before(self, event: Created[Order]) -> None:
        self.log.append(("before", event.entity.id))

    @Created.after
    async def after(self, event: Created[Order], result: Order) -> None:
        self.log.append(("after", event.entity.id, result.id))


async def test_before_runs_before_after():
    s = make_service(PhaseService)
    await s.add(Order(id=3))
    assert s.log == [("before", 3), ("after", 3, 3)]


class BoomRepo(FakeRepo):
    async def add(self, _entity: Any) -> Any:
        raise RuntimeError("boom")


class ErrorService(ModelService[Order]):
    log: list

    @Created.on_error
    async def on_error(self, _event: Created[Order], exc: Exception) -> None:
        self.log.append(("error", type(exc).__name__, str(exc)))


async def test_on_error_fires_and_reraises():
    s = ErrorService(repository=BoomRepo())  # type: ignore[arg-type]
    s.log = []
    with pytest.raises(RuntimeError, match="boom"):
        await s.add(Order(id=1))
    assert s.log == [("error", "RuntimeError", "boom")]


# ─────────────────────────────────────────────────────────────────────────
# Priority ordering — lower fires first; ties broken by registration order.
# ─────────────────────────────────────────────────────────────────────────


class PriorityService(ModelService[Order]):
    log: list

    @Created.after(priority=100)
    async def late(self, _event: Created[Order], _result: object) -> None:
        self.log.append("late")

    @Created.after(priority=10)
    async def early(self, _event: Created[Order], _result: object) -> None:
        self.log.append("early")

    @Created.after  # default priority 50
    async def mid(self, _event: Created[Order], _result: object) -> None:
        self.log.append("mid")


async def test_priority_ordering():
    s = make_service(PriorityService)
    await s.add(Order(id=1))
    assert s.log == ["early", "mid", "late"]


# ─────────────────────────────────────────────────────────────────────────
# Wildcard: @BaseEvent.after fires for every event (via MRO dispatch).
# ─────────────────────────────────────────────────────────────────────────


class WildcardService(ModelService[Order]):
    log: list

    @BaseEvent.after
    async def any_event(self, event: BaseEvent, _result: object) -> None:
        self.log.append(type(event).__name__.split("[")[0])  # base name


async def test_wildcard_fires_for_all_events():
    s = make_service(WildcardService)
    await s.add(Order(id=1))
    await s.delete(Order(id=2))
    assert s.log == ["Created", "Deleted"]


# ─────────────────────────────────────────────────────────────────────────
# Custom event — module-level event wired to a custom method via @decorator.
# ─────────────────────────────────────────────────────────────────────────


class Shipped(BaseEvent, wraps="ship"):
    order_id: int
    tracking: str


class ShippingService(ModelService[Order]):
    log: list
    # A custom event fires only when BOTH a wiring source (@emitted_by / wraps=)
    # AND a live namespace entry exist — so it must be declared in `events`.
    events = ModelEventsDict(Shipped=Shipped)

    @Shipped.emitted_by
    async def ship(self, order_id: int, tracking: str) -> None:
        self.log.append(("ship-body", order_id, tracking))

    @Shipped.after
    async def on_shipped(self, event: Shipped, _result: object) -> None:
        self.log.append(("shipped", event.order_id, event.tracking))


async def test_custom_event_fires():
    s = make_service(ShippingService)
    await s.ship(order_id=7, tracking="ABC")
    assert s.log == [("ship-body", 7, "ABC"), ("shipped", 7, "ABC")]


# ─────────────────────────────────────────────────────────────────────────
# Per-service event identity — Created[Order] is distinct from Created[Product].
# ─────────────────────────────────────────────────────────────────────────


class OrderSvc(ModelService[Order]):
    pass


class ProductSvc(ModelService[Product]):
    pass


def test_per_service_event_identity():
    # Access via instances — class-level `Svc.events.X` access trips mypy's
    # generic-instance-var [misc] warning (documented EventsDict caveat).
    o = make_service(OrderSvc)
    p = make_service(ProductSvc)
    assert o.events.Created is not p.events.Created
    assert o.events.Created.__name__ == "Created[Order]"
    assert p.events.Created.__name__ == "Created[Product]"
    # both are subclasses of the base Created (so base handlers fire via MRO)
    assert issubclass(o.events.Created, Created)
    assert issubclass(p.events.Created, Created)


async def test_event_instance_has_parametrized_identity():
    captured: dict[str, str] = {}

    class IdentityService(ModelService[Order]):
        @Created.after
        async def grab(self, event: Created[Order], _result: object) -> None:
            captured["name"] = type(event).__name__

    svc = make_service(IdentityService)
    await svc.add(Order(id=1))
    assert captured["name"] == "Created[Order]"


# ─────────────────────────────────────────────────────────────────────────
# Handler isolation — two services don't fire each other's handlers.
# ─────────────────────────────────────────────────────────────────────────


class ServiceA(ModelService[Order]):
    log: list

    @Created.after
    async def a_handler(self, _event: Created[Order], _result: object) -> None:
        self.log.append("A")


class ServiceB(ModelService[Order]):
    log: list

    @Created.after
    async def b_handler(self, _event: Created[Order], _result: object) -> None:
        self.log.append("B")


async def test_handler_isolation():
    a = make_service(ServiceA)
    b = make_service(ServiceB)
    await a.add(Order(id=1))
    await b.add(Order(id=2))
    assert a.log == ["A"]
    assert b.log == ["B"]


# ─────────────────────────────────────────────────────────────────────────
# Inheritance — subclass inherits parent handlers and adds its own.
# ─────────────────────────────────────────────────────────────────────────


class Parent(ModelService[Order]):
    log: list

    @Created.after
    async def parent_handler(self, _event: Created[Order], _result: object) -> None:
        self.log.append("parent")


class Child(Parent):
    @Created.after
    async def child_handler(self, _event: Created[Order], _result: object) -> None:
        self.log.append("child")


async def test_inherited_handlers_fire():
    c = make_service(Child)
    await c.add(Order(id=1))
    assert "parent" in c.log
    assert "child" in c.log


# ─────────────────────────────────────────────────────────────────────────
# Event payload: frozen + mutable metadata.
# ─────────────────────────────────────────────────────────────────────────


def test_event_frozen():
    e = Created[Order](entity=Order(id=1))
    with pytest.raises(ValidationError):  # frozen model
        e.entity = Order(id=2)  # type: ignore[misc]


def test_event_metadata_mutable():
    e = Created[Order](entity=Order(id=1))
    e.metadata["correlation_id"] = "abc"
    assert e.metadata["correlation_id"] == "abc"


# ─────────────────────────────────────────────────────────────────────────
# 4c-iii: raises / skips / on_hook_error sink (the §6 scenario table).
# A repo that records which methods actually ran (to prove a raising before skips them).
# ─────────────────────────────────────────────────────────────────────────


class TrackingRepo(FakeRepo):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def add(self, entity: Any) -> Any:
        self.calls.append("add")
        return entity


async def test_before_raises_skips_method_and_propagates_bare():
    """before(raises=True) raising → method NOT run, exception propagates BARE."""

    class AbortService(ModelService[Order]):
        @Created.before(raises=True)
        async def gate(self, _event: Created[Order]) -> None:
            raise ValueError("blocked")

    repo = TrackingRepo()
    svc = AbortService(repository=repo)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="blocked"):  # bare, NOT an ExceptionGroup
        await svc.add(Order(id=1))
    assert repo.calls == []  # method body never ran


async def test_before_soft_failure_runs_method():
    """before(raises=False) raising → method STILL runs; failure observed only."""
    seen: list[BaseException] = []

    class SoftService(ModelService[Order]):
        @Created.before(raises=False)
        async def soft(self, _event: Created[Order]) -> None:
            raise RuntimeError("soft")

        @BaseEvent.on_hook_error
        async def sink(self, _event: BaseEvent, errors: ExceptionGroup) -> None:
            seen.extend(errors.exceptions)

    repo = TrackingRepo()
    svc = SoftService(repository=repo)  # type: ignore[arg-type]
    order = Order(id=2)
    result = await svc.add(order)
    assert result is order  # method ran, result returned
    assert repo.calls == ["add"]
    assert [type(e).__name__ for e in seen] == ["RuntimeError"]


async def test_after_failure_does_not_unsucceed_method():
    """after(skips=False) raising → caller still gets the result (no raise)."""

    class AfterFailService(ModelService[Order]):
        @Created.after(skips=False)
        async def boom(self, _event: Created[Order], _result: Order) -> None:
            raise RuntimeError("after-boom")

    svc = AfterFailService(repository=FakeRepo())  # type: ignore[arg-type]
    order = Order(id=3)
    result = await svc.add(order)  # does not raise
    assert result is order


async def test_after_skips_stops_remaining_after_handlers():
    """after(skips=True) raising stops later after-handlers; method still ok."""
    ran: list[str] = []

    class AfterAbortService(ModelService[Order]):
        @Created.after(skips=True, priority=10)
        async def first(self, _event: Created[Order], _result: Order) -> None:
            ran.append("first")
            raise RuntimeError("stop")

        @Created.after(priority=90)
        async def second(self, _event: Created[Order], _result: Order) -> None:
            ran.append("second")

    svc = AfterAbortService(repository=FakeRepo())  # type: ignore[arg-type]
    order = Order(id=4)
    result = await svc.add(order)  # no raise — after never propagates
    assert result is order
    assert ran == ["first"]  # second skipped by skips=True


async def test_on_hook_error_receives_group_on_success_path():
    captured: dict[str, ExceptionGroup] = {}

    class SinkService(ModelService[Order]):
        @Created.before(raises=False)
        async def soft(self, _event: Created[Order]) -> None:
            raise KeyError("k")

        @Created.on_hook_error
        async def sink(self, _event: Created[Order], errors: ExceptionGroup) -> None:
            captured["errors"] = errors

    svc = SinkService(repository=FakeRepo())  # type: ignore[arg-type]
    await svc.add(Order(id=5))
    assert isinstance(captured["errors"], ExceptionGroup)
    assert [type(e).__name__ for e in captured["errors"].exceptions] == ["KeyError"]


async def test_on_hook_error_fires_on_before_raises_and_caller_gets_bare():
    """before-raises path: caller gets the bare exception AND the sink observes it."""
    captured: dict[str, ExceptionGroup] = {}

    class AbortSinkService(ModelService[Order]):
        @Created.before(raises=True)
        async def gate(self, _event: Created[Order]) -> None:
            raise ValueError("blocked")

        @Created.on_hook_error
        async def sink(self, _event: Created[Order], errors: ExceptionGroup) -> None:
            captured["errors"] = errors

    svc = AbortSinkService(repository=FakeRepo())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="blocked"):
        await svc.add(Order(id=6))
    assert [type(e).__name__ for e in captured["errors"].exceptions] == ["ValueError"]


async def test_on_hook_error_sink_raising_is_swallowed():
    """Recursion guard: a sink that raises is swallowed; caller still gets result."""

    class BadSinkService(ModelService[Order]):
        @Created.after(skips=False)
        async def boom(self, _event: Created[Order], _result: Order) -> None:
            raise RuntimeError("after-fail")

        @Created.on_hook_error
        async def bad_sink(self, _event: Created[Order], _errors: ExceptionGroup) -> None:
            raise RuntimeError("sink-itself-fails")

    svc = BadSinkService(repository=FakeRepo())  # type: ignore[arg-type]
    order = Order(id=7)
    result = await svc.add(order)  # does not raise despite the sink blowing up
    assert result is order


async def test_on_error_handler_failure_goes_to_sink_method_exc_stays_bare():
    """Method raises → on_error observes; if on_error itself fails it lands in the
    sink, but the caller still gets the method's BARE exception."""
    captured: dict[str, ExceptionGroup] = {}

    class OnErrBoomRepo(FakeRepo):
        async def add(self, _entity: Any) -> Any:
            raise RuntimeError("method-boom")

    class OnErrService(ModelService[Order]):
        @Created.on_error
        async def observer(self, _event: Created[Order], _exc: Exception) -> None:
            raise KeyError("on-error-fail")

        @Created.on_hook_error
        async def sink(self, _event: Created[Order], errors: ExceptionGroup) -> None:
            captured["errors"] = errors

    svc = OnErrService(repository=OnErrBoomRepo())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="method-boom"):  # method exc, bare
        await svc.add(Order(id=8))
    assert [type(e).__name__ for e in captured["errors"].exceptions] == ["KeyError"]


# ─────────────────────────────────────────────────────────────────────────
# Root BaseEvent wildcard behavior across the hooks.
# ─────────────────────────────────────────────────────────────────────────


async def test_wildcard_before_raises_blocks_every_event():
    """@BaseEvent.before(raises=True) aborts ALL events (add and delete here)."""

    class GlobalGateService(ModelService[Order]):
        @BaseEvent.before(raises=True)
        async def gate(self, _event: BaseEvent) -> None:
            raise PermissionError("denied")

    svc = GlobalGateService(repository=FakeRepo())  # type: ignore[arg-type]
    with pytest.raises(PermissionError):
        await svc.add(Order(id=1))
    with pytest.raises(PermissionError):
        await svc.delete(Order(id=2))


async def test_wildcard_on_hook_error_catches_failures_from_all_events():
    """A single @BaseEvent.on_hook_error sink observes handler failures for any event."""
    seen: list[str] = []

    class GlobalSinkService(ModelService[Order]):
        @Created.after(skips=False)
        async def created_fail(self, _event: Created[Order], _result: Order) -> None:
            raise RuntimeError("created-handler")

        @Deleted.after(skips=False)
        async def deleted_fail(self, _event: Deleted[Order], _result: object) -> None:
            raise RuntimeError("deleted-handler")

        @BaseEvent.on_hook_error
        async def sink(self, event: BaseEvent, _errors: ExceptionGroup) -> None:
            seen.append(type(event).__name__.split("[")[0])

    svc = GlobalSinkService(repository=FakeRepo())  # type: ignore[arg-type]
    await svc.add(Order(id=1))
    await svc.delete(Order(id=2))
    assert seen == ["Created", "Deleted"]


# ─────────────────────────────────────────────────────────────────────────
# on_hook_error is singular: duplicate sinks in ONE body warn; inheritance OK.
# ─────────────────────────────────────────────────────────────────────────


def test_duplicate_sinks_same_event_one_body_warns():
    with pytest.warns(MultipleHookErrorSinksWarning):

        class DupService(ModelService[Order]):
            @Created.on_hook_error
            async def sink_a(self, _event: Created[Order], _errors: ExceptionGroup) -> None: ...

            @Created.on_hook_error
            async def sink_b(self, _event: Created[Order], _errors: ExceptionGroup) -> None: ...


def test_sinks_for_different_events_one_body_no_warn():
    with warnings.catch_warnings():
        warnings.simplefilter("error", MultipleHookErrorSinksWarning)

        class MultiEventService(ModelService[Order]):
            @Created.on_hook_error
            async def created_sink(self, _event: Created[Order], _errors: ExceptionGroup) -> None: ...

            @Updated.on_hook_error
            async def updated_sink(self, _event: Updated[Order], _errors: ExceptionGroup) -> None: ...


def test_inherited_sink_does_not_warn():
    """Inheritance is intentional layering — a child's own single sink never warns,
    even though the parent's sink also fires for the same event."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", MultipleHookErrorSinksWarning)

        class ParentSink(ModelService[Order]):
            @Created.on_hook_error
            async def parent_sink(self, _event: Created[Order], _errors: ExceptionGroup) -> None: ...

        class ChildSink(ParentSink):
            @Created.on_hook_error
            async def child_sink(self, _event: Created[Order], _errors: ExceptionGroup) -> None: ...


# ─────────────────────────────────────────────────────────────────────────
# Wildcard + framework events across MULTIPLE service classes.
#
# Handler registries are per service CLASS (handlers are tagged on methods and
# collected into cls._event_handlers), even though Created/BaseEvent are shared
# module-level classes. So: no cross-service leakage, and each service sees its
# own per-entity event identity (Created[Order] vs Created[Product]).
# ─────────────────────────────────────────────────────────────────────────


TEnt = TypeVar("TEnt", bound=BaseModel)


async def test_wildcard_handlers_isolated_across_services():
    """A @BaseEvent.after on ServiceA must NOT fire when ServiceB runs."""
    log_a: list[str] = []
    log_b: list[str] = []

    class ServiceWildA(ModelService[Order]):
        @BaseEvent.after
        async def any_a(self, event: BaseEvent, _result: object) -> None:
            log_a.append(type(event).__name__.split("[")[0])

    class ServiceWildB(ModelService[Product]):
        @BaseEvent.after
        async def any_b(self, event: BaseEvent, _result: object) -> None:
            log_b.append(type(event).__name__.split("[")[0])

    a = ServiceWildA(repository=FakeRepo())  # type: ignore[arg-type]
    b = ServiceWildB(repository=FakeRepo())  # type: ignore[arg-type]
    await a.add(Order(id=1))
    await b.add(Product(sku="x"))
    # Each log has exactly ONE entry — A's wildcard didn't leak into B's run.
    assert log_a == ["Created"]
    assert log_b == ["Created"]


async def test_framework_event_identity_across_services():
    """@Created.after on two services fires only for its own service, and the
    event carries that service's parametrized identity."""
    seen_a: list[str] = []
    seen_b: list[str] = []

    class OrderSvc2(ModelService[Order]):
        @Created.after
        async def on_a(self, event: Created[Order], _result: object) -> None:
            seen_a.append(type(event).__name__)

    class ProductSvc2(ModelService[Product]):
        @Created.after
        async def on_b(self, event: Created[Product], _result: object) -> None:
            seen_b.append(type(event).__name__)

    a = OrderSvc2(repository=FakeRepo())  # type: ignore[arg-type]
    b = ProductSvc2(repository=FakeRepo())  # type: ignore[arg-type]
    await a.add(Order(id=1))
    await b.add(Product(sku="s"))
    assert seen_a == ["Created[Order]"]  # only A fired, with Order identity
    assert seen_b == ["Created[Product]"]  # only B fired, with Product identity


async def test_shared_generic_base_wildcard_fires_per_subclass_identity():
    """A wildcard handler on a shared generic base service is inherited by each
    subclass and fires with that subclass's own entity identity."""
    seen: list[str] = []

    class SharedAuditBase(ModelService[TEnt]):
        @BaseEvent.after
        async def audit(self, event: BaseEvent, _result: object) -> None:
            seen.append(type(event).__name__)

    class OrderAudited(SharedAuditBase[Order]):
        pass

    class ProductAudited(SharedAuditBase[Product]):
        pass

    await OrderAudited(repository=FakeRepo()).add(Order(id=1))  # type: ignore[arg-type]
    await ProductAudited(repository=FakeRepo()).add(Product(sku="s"))  # type: ignore[arg-type]
    assert seen == ["Created[Order]", "Created[Product]"]


# ─────────────────────────────────────────────────────────────────────────
# Model resolution (hybrid): explicit __model__ wins; else scan all bases;
# else a concrete ModelService subclass raises at class creation.
# ─────────────────────────────────────────────────────────────────────────


class Marker:
    """A plain (non-service) base to force ModelService[X] out of position 0."""


async def test_model_resolved_when_modelservice_not_first_base():
    """ModelService[Order] listed after another base still resolves Order — events
    fire with the parametrized identity (the fix for scanning all __orig_bases__,
    not just the first)."""
    seen: list[str] = []

    class MixedOrderService(Marker, ModelService[Order]):
        @Created.after
        async def on_created(self, event: Created[Order], _result: object) -> None:
            seen.append(type(event).__name__)

    await MixedOrderService(repository=FakeRepo()).add(Order(id=1))  # type: ignore[arg-type]
    assert seen == ["Created[Order]"]  # would be "Created" if the model wasn't resolved


def test_explicit_model_rescues_unresolvable_magic():
    """A forward-ref parametrization the magic can't resolve is rescued by an
    explicit __model__ — events end up parametrized to it."""

    class FwdService(ModelService["Order"]):  # noqa: F821  (forward ref on purpose)
        __model__ = Order

    svc = FwdService(repository=FakeRepo())  # type: ignore[arg-type]
    assert svc.events.Created.__name__ == "Created[Order]"  # instance access (class access trips [misc])


def test_unresolvable_concrete_service_raises():
    """A concrete ModelService subclass whose model can't be determined (forward
    ref, no explicit __model__) fails loudly at class creation."""
    with pytest.raises(TypeError, match="entity model could not be determined"):

        class BrokenService(ModelService["Order"]):  # noqa: F821  (forward ref on purpose)
            pass


def test_generic_base_does_not_require_model():
    """A still-generic service (free TypeVar) is exempt from the model check —
    defining it must not raise."""

    class StillGeneric(ModelService[TEnt]):  # no concrete model — must NOT raise
        pass

    assert issubclass(StillGeneric, ModelService)


# ─────────────────────────────────────────────────────────────────────────
# Mixins (BaseServiceMixin): plain marker classes that contribute handlers and events
# to the service that mixes them in, with no ServiceMeta machinery of their own.
# ─────────────────────────────────────────────────────────────────────────


class Audited(BaseEvent, Generic[TEnt]):
    entity: TEnt


class AuditEventsDict(ModelEventsDict[TEnt], Generic[TEnt]):
    Audited: type[Audited[TEnt]]


class AuditEventsMixin(BaseServiceMixin, Generic[TEnt]):
    events: AuditEventsDict[TEnt] = AuditEventsDict(Audited=Audited)


async def test_mixin_contributes_handler_and_model_resolves_mixin_first():
    """A plain BaseServiceMixin's handler is collected, and the model still resolves
    even though the mixin precedes ModelService in the bases."""
    seen: list[str] = []

    class AuditMixin(BaseServiceMixin):
        @BaseEvent.after
        async def audit(self, event: BaseEvent, _result: object) -> None:
            seen.append(type(event).__name__)

    class OrderService(AuditMixin, ModelService[Order]):
        pass

    await OrderService(repository=FakeRepo()).add(Order(id=1))  # type: ignore[arg-type]
    assert seen == ["Created[Order]"]  # fired AND parametrized (mixin-first ordering)


async def test_plain_non_mixin_base_handlers_not_collected():
    """A plain base that is NOT a BaseServiceMixin does not contribute handlers
    (explicit gate)."""
    seen: list[str] = []

    class NotAMixin:
        @BaseEvent.after
        async def stray(self, _event: BaseEvent, _result: object) -> None:
            seen.append("fired")

    class OrderService(NotAMixin, ModelService[Order]):
        pass

    await OrderService(repository=FakeRepo()).add(Order(id=1))  # type: ignore[arg-type]
    assert seen == []  # not a contributor — handler ignored


async def test_mixin_chain_collects_all_handlers():
    """A mixin inheriting another mixin contributes handlers from both levels."""
    seen: list[str] = []

    class AuditMixin(BaseServiceMixin):
        @Created.after
        async def audit(self, _event: Created[Order], _result: object) -> None:
            seen.append("audit")

    class ExtendedAudit(AuditMixin):
        @Created.after
        async def extra(self, _event: Created[Order], _result: object) -> None:
            seen.append("extra")

    class OrderService(ExtendedAudit, ModelService[Order]):
        pass

    await OrderService(repository=FakeRepo()).add(Order(id=1))  # type: ignore[arg-type]
    assert sorted(seen) == ["audit", "extra"]


async def test_mixin_declares_events_merged_and_parametrized():
    """A mixin's declared events merge into the service namespace and rebind to
    the entity, alongside the framework events. (Escape: the service re-declares
    `events` with the mixin's dict for full typing.)"""

    class OrderService(AuditEventsMixin[Order], ModelService[Order]):
        events: AuditEventsDict[Order]

    svc = OrderService(repository=FakeRepo())  # type: ignore[arg-type]
    assert svc.events.Created.__name__ == "Created[Order]"  # framework event still there
    assert svc.events.Audited.__name__ == "Audited[Order]"  # mixin event, parametrized


# ─────────────────────────────────────────────────────────────────────────
# .contextmanager — structural wrapping hooks (cms). The boundary tier runs
# inside them; cms nest by priority (LIFO), may map the method's exception, and
# a pre-yield raise aborts the operation.
# ─────────────────────────────────────────────────────────────────────────


class MethodBoomRepo(FakeRepo):
    async def add(self, _entity: Any) -> Any:
        raise RuntimeError("low-level")


class DomainError(Exception):
    pass


async def test_contextmanager_wraps_the_boundary():
    """before/after run INSIDE the cm; the cm brackets the whole boundary."""
    log: list[str] = []

    class WrapService(ModelService[Order]):
        @Created.contextmanager
        async def wrap(self, _event: Created[Order]) -> AsyncIterator[None]:
            log.append("enter")
            try:
                yield
                log.append("exit-ok")
            finally:
                log.append("close")

        @Created.after
        async def after(self, _event: Created[Order], _result: object) -> None:
            log.append("after")

    await WrapService(repository=FakeRepo()).add(Order(id=1))  # type: ignore[arg-type]
    assert log == ["enter", "after", "exit-ok", "close"]


async def test_contextmanagers_nest_lifo_by_priority():
    log: list[str] = []

    class NestService(ModelService[Order]):
        @Created.contextmanager(priority=10)
        async def outer(self, _event: Created[Order]) -> AsyncIterator[None]:
            log.append("outer-enter")
            yield
            log.append("outer-exit")

        @Created.contextmanager(priority=20)
        async def inner(self, _event: Created[Order]) -> AsyncIterator[None]:
            log.append("inner-enter")
            yield
            log.append("inner-exit")

    await NestService(repository=FakeRepo()).add(Order(id=1))  # type: ignore[arg-type]
    assert log == ["outer-enter", "inner-enter", "inner-exit", "outer-exit"]


async def test_contextmanager_maps_method_exception():
    """A cm may catch the method's exception and raise a different one."""

    class MapService(ModelService[Order]):
        @Created.contextmanager
        async def mapper(self, _event: Created[Order]) -> AsyncIterator[None]:
            try:
                yield
            except RuntimeError as exc:
                raise DomainError("mapped") from exc

    svc = MapService(repository=MethodBoomRepo())  # type: ignore[arg-type]
    with pytest.raises(DomainError, match="mapped") as excinfo:
        await svc.add(Order(id=1))
    assert isinstance(excinfo.value.__cause__, RuntimeError)  # original chained


async def test_contextmanager_pre_yield_raise_aborts_method():
    """A raise before `yield` aborts: the method never runs, exception is bare."""

    class AbortRepo(FakeRepo):
        def __init__(self) -> None:
            self.called = False

        async def add(self, entity: Any) -> Any:
            self.called = True
            return entity

    class GateService(ModelService[Order]):
        @Created.contextmanager
        async def gate(self, _event: Created[Order]) -> AsyncIterator[None]:
            raise PermissionError("blocked")
            yield  # unreachable — present only to make this an async generator

    repo = AbortRepo()
    svc = GateService(repository=repo)  # type: ignore[arg-type]
    with pytest.raises(PermissionError, match="blocked"):
        await svc.add(Order(id=1))
    assert repo.called is False


async def test_contextmanager_suppressing_without_result_is_an_error():
    """Swallowing the method's exception without a result is unsupported and
    raises a clear error (result-replacement is the deferred follow-up)."""

    class SwallowService(ModelService[Order]):
        @Created.contextmanager
        async def swallow(self, _event: Created[Order]) -> AsyncIterator[None]:
            with contextlib.suppress(RuntimeError):  # swallow, no re-raise — no result
                yield

    svc = SwallowService(repository=MethodBoomRepo())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="suppressed the operation"):
        await svc.add(Order(id=1))


# ─────────────────────────────────────────────────────────────────────────
# Wiring Sources Policy (design.md §2): one method, one event.
#   (a) wraps= only, no @emitted_by anywhere in MRO   → silent, first-class style
#   (b) @emitted_by only, no wraps=                    → silent, first-class style
#   (c) sources name different events (not MRO-compat) → TypeError at class creation
#   (d) multiple @emitted_by stacked on one method     → TypeError at class creation
# ─────────────────────────────────────────────────────────────────────────


def test_policy_a_wraps_only_is_silent() -> None:
    """(a) — `wraps=` on the event, no `@emitted_by` anywhere: a first-class,
    silent wiring style. The wrapper is still installed."""

    class CustomEvent(BaseEvent, wraps="custom_method"):
        pass

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning → test fails

        class MagicSvc(BaseService):
            events = EventsDict(CustomEvent=CustomEvent)

            async def custom_method(self) -> None:
                pass

    assert getattr(MagicSvc.custom_method, "__furious_wrapped__", False)


def test_policy_b_emitted_by_only_silent_pass() -> None:
    """(b) — `@emitted_by` on the method, event has no `wraps=`. No warning,
    no error; this is a first-class declaration style."""

    class MethodAnchoredEvent(BaseEvent):  # no wraps=
        pass

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning → test fails

        class MASvc(BaseService):
            events = EventsDict(MethodAnchoredEvent=MethodAnchoredEvent)

            @MethodAnchoredEvent.emitted_by
            async def m(self) -> None:
                pass

    assert getattr(MASvc.m, "__furious_wrapped__", False)


def test_policy_c_disagreement_raises() -> None:
    """(c) — wraps= names A but @emitted_by names B (unrelated). Silent-lie
    bug; must raise at class-creation time."""

    class EventA(BaseEvent, wraps="m"):
        pass

    class EventB(BaseEvent):
        pass

    with pytest.raises(TypeError, match="incompatible events"):

        class DisagreeSvc(BaseService):
            events = EventsDict(EventA=EventA, EventB=EventB)

            @EventB.emitted_by
            async def m(self) -> None:
                pass


def test_policy_d_stacked_emitted_by_raises() -> None:
    """(d) — multiple `@emitted_by` decorators on one method. Must raise with
    a refactor hint pointing at the sequential-method pattern."""

    class EventA(BaseEvent):
        pass

    class EventB(BaseEvent):
        pass

    with pytest.raises(TypeError, match="multiple `@emitted_by`"):

        class StackedSvc(BaseService):
            @EventA.emitted_by
            @EventB.emitted_by
            async def m(self) -> None:
                pass


def test_policy_d_message_includes_refactor_hint() -> None:
    """The (d) error must teach the sequential refactor — not just reject."""

    class A(BaseEvent):
        pass

    class B(BaseEvent):
        pass

    with pytest.raises(TypeError) as exc_info:

        class _S(BaseService):
            @A.emitted_by
            @B.emitted_by
            async def add(self) -> None:
                pass

    msg = str(exc_info.value)
    assert "self.publish" in msg
    assert ".emitted_by" in msg
    assert "design.md" in msg


def test_policy_sources_agree_no_warn_no_error() -> None:
    """The framework-default pattern (and any user pattern matching it): both
    sources name the same event. Silent pass — no warning, no error."""

    class AgreeEvent(BaseEvent, wraps="m"):
        pass

    with warnings.catch_warnings():
        warnings.simplefilter("error")

        class AgreeSvc(BaseService):
            events = EventsDict(AgreeEvent=AgreeEvent)

            @AgreeEvent.emitted_by
            async def m(self) -> None:
                pass

    assert getattr(AgreeSvc.m, "__furious_wrapped__", False)


def test_policy_model_service_defaults_no_warning() -> None:
    """ModelService's defaults sit at (a)∩(b) where wraps= and @emitted_by
    agree per-method. Defining a subclass must not emit the magic warning."""

    with warnings.catch_warnings():
        warnings.simplefilter("error")

        class PlainSvc(ModelService[Order]):
            pass

    assert PlainSvc.__model__ is Order  # type: ignore[misc]  # class access to generic instance var (cosmetic)


def test_policy_mro_compatible_generic_and_param() -> None:
    """`Created` (generic) and `Created[Order]` (parametrized) are in one MRO
    chain. The framework re-parametrizes events per-service, which means
    `wraps=` on the generic and `@emitted_by` on the parametrized variant
    coexist routinely — must not trigger the disagreement check."""

    # The flagship case: ModelService[Order] has both — wraps= on the generic
    # Created (inherited via __wraps_methods__) and the framework decorator
    # `@Created.emitted_by` on `add`, re-parametrized to Created[Order] in
    # the per-service events namespace. Construction must succeed silently.
    with warnings.catch_warnings():
        warnings.simplefilter("error")

        class _OrderSvc(ModelService[Order]):
            pass


def test_policy_override_without_redecorating_inherits_wiring() -> None:
    """A subclass overrides a decorated method without re-decorating. The
    parent's `@emitted_by` is found via the MRO walk on the parent's version
    of the method, so wiring is preserved — case (a) does NOT warn here."""

    with warnings.catch_warnings():
        warnings.simplefilter("error")

        class OverrideSvc(ModelService[Order]):
            async def add(self, entity: Order) -> Order:
                return await self.repository.add(entity)


def test_policy_d_in_mixin_raises_at_consumer() -> None:
    """A mixin carrying stacked decorators triggers (d) when a service uses
    it. The error message names the mixin as the defining class."""

    class A(BaseEvent):
        pass

    class B(BaseEvent):
        pass

    class StackedMixin(BaseServiceMixin):
        @A.emitted_by
        @B.emitted_by
        async def m(self) -> None:
            pass

    with pytest.raises(TypeError, match=r"StackedMixin\.m"):

        class _UsesMixin(StackedMixin, BaseService):
            pass
