"""Path B: class-creation-time validation of the name-match join (design.md §4).

``_build_event`` fills an event's fields from the wrapped method's call arguments
by name. ``install_wrappers`` validates, at class-creation time, that every
*required* event field has a same-named parameter in the method it wraps — turning
a silent empty-payload bug into a loud ``TypeError`` at import. Optional fields
(those with defaults, e.g. ``Updated``'s ``id_``/``entity``, which ``patch`` does
not fully supply) are exempt.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from furiousapi.service import BaseEvent, Deleted
from furiousapi.service.base import ModelService


class Order(BaseModel):
    id_: int = 0
    name: str = ""


class _Repo:  # minimal async repo stub — only the CRUD methods ModelService delegates to
    async def add(self, entity: Any) -> Any:
        return entity

    async def patch(self, id_: Any, partial: Any) -> Any:
        return Order(id_=id_, name=partial.get("name", ""))

    async def replace(self, _id: Any, entity: Any) -> Any:
        return entity

    async def delete(self, _entity: Any) -> None:
        return None


class OrderService(ModelService[Order]):
    """Concrete framework-defaults service; events come from ModelService."""


def test_required_field_without_matching_param_raises() -> None:
    """A method wired to an event whose required field names no parameter is a
    silent-empty-payload bug — caught loudly at class definition."""

    class Greeted(BaseEvent):
        addr: str  # required, but `greet` below exposes `body`, not `addr`

    with pytest.raises(TypeError, match="required field"):

        class _Bad(OrderService):
            @Greeted.emitted_by
            async def greet(self, body: str) -> None: ...


@pytest.mark.asyncio
async def test_required_field_with_matching_param_ok() -> None:
    """Same required field, but the parameter name matches — the class defines
    cleanly and the value flows into the event payload via the name-match join."""
    seen: dict[str, Any] = {}

    class Greeted(BaseEvent):
        addr: str

    class Good(OrderService):
        @Greeted.before
        async def _capture(self, event: Greeted) -> None:
            seen["addr"] = event.addr

        @Greeted.emitted_by
        async def greet(self, addr: str) -> None: ...

    await Good(repository=_Repo()).greet("a@b.com")  # type: ignore[arg-type]
    assert seen == {"addr": "a@b.com"}


@pytest.mark.asyncio
async def test_optional_field_without_matching_param_ok() -> None:
    """An optional field (has a default) is allowed to go unfilled — its default
    expresses exactly that — so no matching parameter is required, and the event
    builds with the default."""
    seen: dict[str, Any] = {}

    class Greeted(BaseEvent):
        addr: str | None = None  # optional ⇒ exempt from the check

    class Good(OrderService):
        @Greeted.before
        async def _capture(self, event: Greeted) -> None:
            seen["addr"] = event.addr

        @Greeted.emitted_by
        async def greet(self, body: str) -> None: ...

    await Good(repository=_Repo()).greet("ignored")  # type: ignore[arg-type]
    assert seen == {"addr": None}


def test_framework_defaults_satisfy_the_check() -> None:
    """The framework's own CRUD wiring passes the check: every required event field
    is named by the method it wraps — Created.entity↔add(entity),
    Deleted.entity↔delete(entity). (Updated's id_/entity are optional.)"""

    class Svc(ModelService[Order]):  # would raise at definition if the check failed
        pass

    assert Svc.__model__ is Order  # type: ignore[misc]  # class access to a generic instance var (cosmetic)
    # Deleted.entity is required and the join holds because delete names its
    # parameter `entity` — the required-field check is exactly what guarantees that.
    assert Deleted.model_fields["entity"].is_required() is True


@pytest.mark.asyncio
async def test_deleted_carries_entity_from_matching_param() -> None:
    """The matching `entity` parameter flows into the required `Deleted.entity`
    field via the name-match join the check guards."""
    seen: dict[str, Any] = {}

    class Svc(OrderService):
        @Deleted.before
        async def _capture(self, event: Deleted[Order]) -> None:
            seen["entity"] = event.entity

    order = Order(id_=7, name="x")
    await Svc(repository=_Repo()).delete(order)  # type: ignore[arg-type]
    assert seen["entity"] == order
