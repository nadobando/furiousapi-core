"""ModelEvent layer + Partial[T] input view (design.md §4).

Two axes the hierarchy encodes:
- entity-coupled (`Created`/`Updated`/`Deleted` < `ModelEvent`) vs not (`Sent` < `BaseEvent`)
- input/trigger (`patch`'s `partial`) vs output/fact (`entity`)

The headline win: a `before` handler on `patch` can see the requested change via
`event.partial` — a `Partial[T]` (all fields optional), not a stripped full entity.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from furiousapi.service import (
    BaseEvent,
    Created,
    Deleted,
    ModelEvent,
    ModelService,
    Partial,
    Updated,
    make_partial,
)


class Order(BaseModel):
    id_: int
    name: str = "x"
    status: str = "new"


class FakeRepo:
    async def add(self, entity: Any) -> Any:
        return entity

    async def patch(self, _id: Any, partial: Any, **_kwargs: Any) -> Any:
        return partial

    async def replace(self, _id: Any, entity: Any, **_kwargs: Any) -> Any:
        return entity

    async def delete(self, _entity: Any, **_kwargs: Any) -> None:
        return None


def make(service_cls: type) -> Any:
    svc = service_cls(repository=FakeRepo())
    svc.log = []
    return svc


# ── Axis A: entity-coupling hierarchy ──────────────────────────────────────


def test_crud_events_are_model_events() -> None:
    assert issubclass(Created, ModelEvent)
    assert issubclass(Updated, ModelEvent)
    assert issubclass(Deleted, ModelEvent)
    # parametrized variants too (MRO carries through pydantic generics)
    assert issubclass(Created[Order], ModelEvent)


def test_non_entity_event_is_not_a_model_event() -> None:
    class Sent(BaseEvent, wraps="send"):
        recipient: str
        template: str

    assert not issubclass(Sent, ModelEvent)
    assert issubclass(Sent, BaseEvent)


def test_custom_non_entity_event_with_required_fields() -> None:
    """A Shipped-style custom event (required fields, no entity) sits OUTSIDE the
    ModelEvent layer AND passes the Path B required-field check, because every
    required field name-matches a `ship` parameter — locking what is otherwise
    only incidentally true."""

    class Shipped(BaseEvent, wraps="ship"):
        order_id: int
        tracking: str

    assert not issubclass(Shipped, ModelEvent)  # not entity-coupled

    class Svc(ModelService[Order]):  # defines cleanly ⇒ Path B passed (no TypeError)
        @Shipped.emitted_by
        async def ship(self, order_id: int, tracking: str) -> None: ...

    assert "ship" in vars(Svc)


async def test_model_event_is_a_wildcard_target() -> None:
    """@ModelEvent.after fires for any entity-lifecycle event of any model."""
    seen: list[str] = []

    class Svc(ModelService[Order]):
        @ModelEvent.after
        async def audit(self, event: ModelEvent[Order], _result: object) -> None:
            seen.append(type(event).__name__)

    s = make(Svc)
    await s.add(Order(id_=1))
    await s.replace(2, Order(id_=2))
    await s.delete(Order(id_=3))
    assert seen == ["Created[Order]", "Updated[Order]", "Deleted[Order]"]


# ── Axis B: input (partial) vs output (entity) ─────────────────────────────


async def test_patch_before_sees_partial_change() -> None:
    """The headline fix: a `before` handler on patch sees the requested change."""
    seen: dict[str, Any] = {}

    class Svc(ModelService[Order]):
        @Updated.before
        async def guard(self, event: Updated[Order]) -> None:
            seen["partial"] = event.partial
            seen["entity"] = event.entity

    await make(Svc).patch(7, {"status": "shipped"})
    partial = seen["partial"]
    assert partial is not None
    assert partial.model_dump(exclude_unset=True) == {"status": "shipped"}
    assert seen["entity"] is None  # no full entity at patch-input time


async def test_replace_before_sees_full_entity() -> None:
    seen: dict[str, Any] = {}

    class Svc(ModelService[Order]):
        @Updated.before
        async def guard(self, event: Updated[Order]) -> None:
            seen["partial"] = event.partial
            seen["entity"] = event.entity

    order = Order(id_=9, name="real")
    await make(Svc).replace(9, order)
    assert seen["partial"] is None
    assert seen["entity"] == order


# ── Partial[T] primitive ───────────────────────────────────────────────────


def test_partial_is_distinct_optional_mirror() -> None:
    partial_order = make_partial(Order)
    assert not issubclass(partial_order, Order)  # honest: a distinct type, not full T
    # every field optional → any subset validates
    assert partial_order(status="shipped").model_dump(exclude_unset=True) == {"status": "shipped"}
    assert partial_order().model_dump(exclude_unset=True) == {}


def test_partial_validation_still_real() -> None:
    partial_order = make_partial(Order)
    with pytest.raises(ValidationError):
        partial_order(id_="not-an-int")


def test_partial_is_cached() -> None:
    assert make_partial(Order) is make_partial(Order)


def test_partial_field_coerces_in_event() -> None:
    u = Updated[Order](id_=1, partial={"status": "shipped"})  # type: ignore[arg-type]  # dict→partial coercion
    assert type(u.partial).__name__ == "PartialOrder"
    assert u.partial is not None
    assert u.partial.status == "shipped"


def test_partial_mirror_is_plain_basemodel_not_source_metaclass() -> None:
    """SQLModel/Beanie safety: the mirror is a plain BaseModel built by copying
    field annotations — the source model's metaclass is never re-run."""
    from pydantic._internal._model_construction import ModelMetaclass

    partial_order = make_partial(Order)
    assert type(partial_order) is ModelMetaclass


def test_partial_alias_constructs_via_subscription() -> None:
    u = Updated[Order](partial={"name": "z"})  # type: ignore[arg-type]  # dict→partial coercion
    assert u.partial is not None
    assert u.partial.name == "z"


def test_partial_helper_usable_on_custom_event() -> None:
    """`Partial[Order]` works as a field type on a user-defined event, yielding
    the same all-optional behavior as the framework's `Updated.partial`."""

    class Patched(BaseEvent):
        changes: Partial[Order]

    # model_validate (typed to accept Any) exercises the same field coercion the
    # constructor would, without the dict→partial arg-type friction.
    p = Patched.model_validate({"changes": {"status": "shipped"}})
    assert p.changes is not None
    assert p.changes.model_dump(exclude_unset=True) == {"status": "shipped"}
