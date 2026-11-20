"""Event subscribers for the webhooks domain."""

import logging
from typing import TYPE_CHECKING

from airweave.core.events.enums import SearchEventType

if TYPE_CHECKING:
    from airweave.core.protocols import WebhookPublisher
    from airweave.core.protocols.event_bus import DomainEvent

logger = logging.getLogger(__name__)

#: Gooclaim (2026-11-20): search events are not sent as webhooks. No one subscribes to
#: them (gooclaim-audit takes sync and connection events), yet each was a Svix create +
#: list INSIDE the search's own response — ~250 ms of a 480 ms warm search on dev — and
#: kept every search's results in Svix. Every other event is forwarded as before.
_NOT_SENT = frozenset(SearchEventType)


class WebhookEventSubscriber:
    """Forwards domain events to external webhook endpoints.

    Subscribes to all events (``*``) and delegates directly to the
    :class:`WebhookPublisher`.  The publisher (adapter) is responsible
    for serializing the event; this subscriber just routes.
    """

    EVENT_PATTERNS = ["*"]

    def __init__(self, publisher: "WebhookPublisher") -> None:
        """Initialize with a webhook publisher."""
        self._publisher = publisher

    async def handle(self, event: "DomainEvent") -> None:
        """Forward a domain event to the webhook publisher."""
        if event.event_type in _NOT_SENT:
            return
        event_type = str(event.event_type)
        logger.debug(f"WebhookEventSubscriber: forwarding '{event_type}' to webhook publisher")
        await self._publisher.publish_event(event)
