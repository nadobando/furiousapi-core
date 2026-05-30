"""Service-layer events: IDE-autocomplete check + runtime firing demo.

Two purposes:

1. **Manual IDE check** — hover / autocomplete at the marked spots to confirm
   the entity type propagates (``event.entity.<TAB>`` shows Order's fields).
2. **Runtime firing demo** — run it (``python example/service_events_example.py``)
   to watch CRUD events and a custom event actually fire, with per-service
   event identity (``Created[Order]``) and a custom ``OrderShipped`` event.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from furiousapi.service import BaseEvent, Created, ModelService

if TYPE_CHECKING:
    from furiousapi.db.repository import BaseRepository


# --- A concrete entity with distinctive fields so autocomplete is obvious ---
class Order(BaseModel):
    id: int
    customer_name: str
    total_cents: int


# --- A custom (non-CRUD) event, wired to a custom `ship` method ---
# Custom events live at module level and bind via the `@OrderShipped` decorator
# on the method (the event isn't in ModelService's events dict, so the decorator
# is what wires it). `wraps="ship"` is kept for self-description.
class OrderShipped(BaseEvent, wraps="ship"):
    order_id: int
    tracking: str


# --- A fake repository so we can construct the service without a real DB ---
class FakeOrderRepository:
    async def add(self, entity: Order) -> Order:
        return entity

    async def get(self, identifiers, fields=None, *, should_error=True) -> Order | None:
        return None

    async def patch(self, id_, partial, **kwargs) -> Order | None:
        return Order(id=id_, customer_name="patched", total_cents=0)

    async def replace(self, id_, entity, **kwargs) -> Order | None:
        return entity

    async def delete(self, entity, **kwargs) -> None:
        return None

    async def bulk_create(self, bulk):
        return bulk

    async def bulk_update(self, bulk):
        return bulk

    async def bulk_delete(self, bulk):
        return bulk


class OrderService(ModelService[Order]):
    # ── Handlers for the framework CRUD events ──
    @Created.before
    async def check_total(self, event: Created[Order]) -> None:
        print(f"  [handler] {type(event).__name__}.before total_cents={event.entity.total_cents}")

    @Created.after
    async def on_created(self, event: Created[Order], result: Order) -> None:
        # event is Created[Order] at runtime; event.entity is an Order.
        print(f"  [handler] {type(event).__name__}.after  entity.id={event.entity.id}")

    # ── A custom method that fires the custom OrderShipped event ──
    @OrderShipped.emitted_by
    async def ship(self, order_id: int, tracking: str) -> None:
        print(f"  [method]  ship(order_id={order_id}, tracking={tracking!r})")

    @OrderShipped.after
    async def notify_carrier(self, event: OrderShipped, result) -> None:
        print(f"  [handler] {type(event).__name__}.after  order_id={event.order_id} tracking={event.tracking!r}")


async def main() -> None:
    repo = cast("BaseRepository[Order]", FakeOrderRepository())
    service = OrderService(repository=repo)

    # ──────────────────────────────────────────────────────────────────────
    # AUTOCOMPLETE CHECK — instance access through the events namespace.
    # Hover `service.events.Created` → type[Created[Order]]
    #     event.entity.<TAB> → id / customer_name / total_cents (NOT Any)
    # ──────────────────────────────────────────────────────────────────────
    event = service.events.Created(entity=Order(id=1, customer_name="Ada", total_cents=4200))
    print("AUTOCOMPLETE CHECK:")
    print(f"  events.Created is {service.events.Created.__name__}")
    print(f"  event.entity.customer_name = {event.entity.customer_name}")
    print()

    # ──────────────────────────────────────────────────────────────────────
    # FIRING DEMO — CRUD events fire with per-service identity (Created[Order]).
    # ──────────────────────────────────────────────────────────────────────
    print("add() → fires Created[Order]:")
    await service.add(Order(id=7, customer_name="Linus", total_cents=999))
    print()

    print("ship() → fires the custom OrderShipped event:")
    await service.ship(order_id=7, tracking="TRACK-123")


if __name__ == "__main__":
    asyncio.run(main())
