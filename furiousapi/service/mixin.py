"""Marker base for service mixins.

Lives in its own module so neither ``base.py`` nor ``events.py`` has to own
it: ``base.py`` would need an ``events.py`` import to re-export it, and
``events.py`` (which keys handler collection on it) would mix the event
machinery with the public mixin contract. A dedicated module breaks both
ties — both modules import from here, and the public import path stays
stable through ``furiousapi.service``.
"""

from __future__ import annotations


class BaseServiceMixin:
    """Marker base for service mixins.

    A **plain class** — it carries none of ``ServiceMeta``'s machinery (no
    model extraction, no event rebinding, no wrapper install). A mixin only
    *contributes* handlers (and optionally an ``events`` namespace) to the
    service that mixes it in; it is never instantiated as a service itself.
    ``furiousapi.service.events._is_contributor`` recognises it via
    ``issubclass`` when walking the MRO to collect handlers and events.
    """
