"""Runtime behavior tests for the service-layer event system.

Covers: CRUD event firing, the three phases (before/after/on_error), handler
args, priority ordering, wildcard dispatch, custom events, per-service event
identity, handler isolation, and inheritance.

Unused handler args are ``_``-prefixed (the framework calls handlers
positionally, so the name doesn't matter for dispatch — the prefix just signals
"intentionally unused").
"""

from __future__ import annotations

from typing import Any, TypeVar

import pytest
from pydantic import BaseModel, ValidationError

from furiousapi.service import BaseEvent, Created, Deleted, ModelService, Updated


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
