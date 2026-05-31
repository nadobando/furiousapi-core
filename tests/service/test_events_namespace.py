"""Events-namespace customization: autobind / customize / extend / replace / veto.

Covers the namespace-as-source-of-truth model (design doc
``events-namespace-customization.md``):

* ``ModelEventsDict`` = EXTEND base (ships CRUD defaults).
* ``EventsDict`` = REPLACE base (no defaults; only what you list is live).
* ``None`` slot = per-key veto → that method runs raw.
* Firing requires BOTH a wiring source (``wraps=`` / ``@emitted_by``) AND a live
  namespace entry. Neither alone fires.

These lock the runtime wiring (collect_events base-awareness + namespace-driven
install_wrappers). The class-form ``class Events:`` surface is a separate step.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from furiousapi.service import (
    BaseEvent,
    BaseServiceMixin,
    Created,
    EventsDict,
    ModelEventsDict,
    ModelService,
    Updated,
)

WRAPPED = "__furious_wrapped__"


class Order(BaseModel):
    id_: int = 0
    name: str = "x"


class FakeRepo:
    async def add(self, entity: Any) -> Any:
        return entity

    async def patch(self, _id: Any, partial: Any, **_kwargs: Any) -> Any:
        return partial

    async def replace(self, _id: Any, entity: Any, **_kwargs: Any) -> Any:
        return entity

    async def delete(self, _entity: Any, **_kwargs: Any) -> None:
        return None


class MyCreated(Created[Order]):
    note: str = ""


class Shipped(BaseEvent, wraps="ship"):
    tracking: str = ""


def make(service_cls: type) -> Any:
    return service_cls(repository=FakeRepo())


def is_wrapped(cls: type, method: str) -> bool:
    return getattr(getattr(cls, method), WRAPPED, False)


# ── #1: ModelEventsDict ships CRUD defaults; EventsDict does not ───────────


def test_model_events_dict_self_seeds_crud() -> None:
    assert sorted(ModelEventsDict()) == ["Created", "Deleted", "Updated"]


def test_events_dict_is_empty_by_default() -> None:
    assert list(EventsDict()) == []


def test_override_one_keeps_other_defaults() -> None:
    d: ModelEventsDict[Order] = ModelEventsDict(Created=MyCreated)
    assert d["Created"] is MyCreated
    assert "Updated" in d
    assert "Deleted" in d


def test_none_is_preserved_as_value_not_dropped() -> None:
    d: ModelEventsDict[Order] = ModelEventsDict(Updated=None)
    assert "Updated" in d
    assert d["Updated"] is None


# ── #2: collect_events is base-aware (extend vs replace), mixins kept ──────


def test_autobind_default_service() -> None:
    class Svc(ModelService[Order]):
        pass

    assert sorted(Svc.events) == ["Created", "Deleted", "Updated"]  # type: ignore[misc]  # class access to generic instance var
    assert Svc.events["Created"].__name__ == "Created[Order]"  # type: ignore[misc]


def test_extend_overrides_one_autobinds_rest() -> None:
    class Svc(ModelService[Order]):
        events = ModelEventsDict(Created=MyCreated)

    assert Svc.events["Created"] is MyCreated
    assert Svc.events["Updated"].__name__ == "Updated[Order]"
    assert Svc.events["Deleted"].__name__ == "Deleted[Order]"


def test_replace_drops_inherited_crud() -> None:
    class Svc(ModelService[Order]):
        # Replace form narrows ModelEventsDict[Order] → EventsDict; mypy flags the
        # assignment, accepted by design (use the class form for a warning-free path).
        events: ModelEventsDict[Order] = EventsDict(Created=MyCreated)  # type: ignore[assignment]

    assert list(Svc.events) == ["Created"]


def test_replace_with_only_a_new_event() -> None:
    class Svc(ModelService[Order]):
        events: ModelEventsDict[Order] = EventsDict(Shipped=Shipped)  # type: ignore[assignment]

        @Shipped.emitted_by
        async def ship(self, tracking: str) -> None: ...

    assert list(Svc.events) == ["Shipped"]


def test_replace_keeps_mixin_events() -> None:
    class AuditMixin(BaseServiceMixin):
        events: EventsDict[Order] = EventsDict(Shipped=Shipped)

    class Svc(AuditMixin, ModelService[Order]):
        events: ModelEventsDict[Order] = EventsDict(Created=MyCreated)  # type: ignore[assignment]

        @Shipped.emitted_by
        async def ship(self, tracking: str) -> None: ...

    assert sorted(Svc.events) == ["Created", "Shipped"]


# ── #3: emission follows the namespace (wrapping + behavior) ───────────────


def test_default_wraps_all_crud() -> None:
    class Svc(ModelService[Order]):
        pass

    assert (is_wrapped(Svc, "add"), is_wrapped(Svc, "patch"), is_wrapped(Svc, "delete")) == (True, True, True)


def test_replace_only_wraps_listed_methods() -> None:
    class Svc(ModelService[Order]):
        events: ModelEventsDict[Order] = EventsDict(Created=MyCreated)  # type: ignore[assignment]

    assert is_wrapped(Svc, "add") is True
    assert is_wrapped(Svc, "patch") is False
    assert is_wrapped(Svc, "delete") is False


def test_veto_unwraps_that_method_only() -> None:
    class Svc(ModelService[Order]):
        events = ModelEventsDict(Updated=None)

    assert is_wrapped(Svc, "add") is True
    assert is_wrapped(Svc, "patch") is False
    assert is_wrapped(Svc, "delete") is True


async def test_vetoed_method_runs_raw_emits_nothing() -> None:
    fired: list[str] = []

    class Svc(ModelService[Order]):
        events = ModelEventsDict(Updated=None)

        @Updated.before
        async def guard(self, _event: Updated[Order]) -> None:
            fired.append("updated")

    await make(Svc).patch(1, Order(id_=1))  # vetoed → raw → guard must NOT fire
    assert fired == []


async def test_replace_method_runs_raw_emits_nothing() -> None:
    fired: list[str] = []

    class Svc(ModelService[Order]):
        events: ModelEventsDict[Order] = EventsDict(Created=MyCreated)  # type: ignore[assignment]

        @Updated.before
        async def guard(self, _event: Updated[Order]) -> None:
            fired.append("updated")

    await make(Svc).patch(1, Order(id_=1))  # Updated not in namespace → raw
    assert fired == []


def test_all_none_equiv_to_empty_replace() -> None:
    class AllOff(ModelService[Order]):
        events = ModelEventsDict(Created=None, Updated=None, Deleted=None)

    class Empty(ModelService[Order]):
        events: ModelEventsDict[Order] = EventsDict()  # type: ignore[assignment]

    for svc in (AllOff, Empty):
        assert is_wrapped(svc, "add") is False
        assert is_wrapped(svc, "patch") is False
        assert is_wrapped(svc, "delete") is False


# ── deep chain: parent wraps, child vetoes (the explicitly-untested path) ──


async def test_child_veto_overrides_parent_wrapping() -> None:
    parent_fired: list[str] = []

    class Parent(ModelService[Order]):
        @Updated.before
        async def guard(self, _event: Updated[Order]) -> None:
            parent_fired.append("updated")

    assert is_wrapped(Parent, "patch") is True  # parent wraps patch (default)

    class Child(Parent):
        events = ModelEventsDict(Updated=None)  # veto the inherited event

    assert is_wrapped(Child, "patch") is False

    await make(Child).patch(1, Order(id_=1))
    assert parent_fired == []  # child runs raw despite parent's wrapper


async def test_parent_still_emits_after_child_veto() -> None:
    """Child's veto must not corrupt the parent's own wrapper (shadow, not mutate)."""
    fired: list[str] = []

    class Parent(ModelService[Order]):
        @Updated.before
        async def guard(self, _event: Updated[Order]) -> None:
            fired.append("p")

    class Child(Parent):
        events = ModelEventsDict(Updated=None)

    make(Child)  # force Child creation/wiring
    await make(Parent).patch(1, Order(id_=1))
    assert fired == ["p"]  # parent unaffected


# ── the AND-rule: both wiring source AND namespace entry required ──────────


async def test_custom_event_needs_namespace_and_wiring() -> None:
    log: list[str] = []

    # wired via @emitted_by AND declared in namespace → fires
    class Live(ModelService[Order]):
        events = ModelEventsDict(Shipped=Shipped)

        @Shipped.emitted_by
        async def ship(self, tracking: str) -> None: ...

        @Shipped.after
        async def on_ship(self, event: Shipped, _r: object) -> None:
            log.append(event.tracking)

    assert is_wrapped(Live, "ship") is True
    await make(Live).ship("ABC")
    assert log == ["ABC"]


def test_custom_event_wired_but_not_in_namespace_is_inert() -> None:
    # @emitted_by present, but Shipped NOT in the (replace) namespace → not wrapped
    class Dormant(ModelService[Order]):
        events: ModelEventsDict[Order] = EventsDict(Created=MyCreated)  # type: ignore[assignment]

        @Shipped.emitted_by
        async def ship(self, tracking: str) -> None: ...

    assert is_wrapped(Dormant, "ship") is False
