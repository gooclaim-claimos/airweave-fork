"""Gooclaim: every tenant's data-sources events reach the audit ledger.

gooclaim-audit receives this fork's events at `POST /v1/audit/airweave-webhook` and writes
them to the ledger — a sync completed or failed, a source connected or removed: the
evidence of what entered a tenant's library. Until 2026-11-20 no Svix endpoint was
registered for any tenant, so not one of those events ever reached it.

Each tenant's Svix application gets ONE endpoint, uid `gooclaim-audit`, subscribed to
exactly the four channels the ledger takes. It is made the first time this process
publishes one of those events for the tenant — BEFORE the message, so that event is
delivered too — and not looked at again by this process. A tenant created tomorrow gets
it the same way. If it already exists, its address and channels are brought up to date.
No address configured → nothing happens (upstream behaviour).

Never raises: if the endpoint cannot be made, the event still goes to Svix (logged).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from svix.api import ApplicationIn, EndpointIn, EndpointPatch

logger = logging.getLogger(__name__)

#: The fork's event names the ledger records (gooclaim-audit `_EVENT_MAP`).
AUDIT_CHANNELS: tuple[str, ...] = (
    "sync.completed",
    "sync.failed",
    "source_connection.created",
    "source_connection.deleted",
)
ENDPOINT_UID = "gooclaim-audit"


def _code(exc: Exception) -> str:
    return str(getattr(exc, "code", "") or "")


class AuditEndpoint:
    """Makes sure a tenant's Svix application has the audit ledger's endpoint."""

    def __init__(self, svix: Any, url: str, secret: str) -> None:
        """`svix` is the adapter's `SvixAsync`; `url` empty switches this off."""
        self._svix = svix
        self._url = url.strip()
        self._secret = secret.strip() or None
        self._ready: set[str] = set()

    async def ensure(self, org_id: uuid.UUID, event_type: str) -> None:
        """Before an audited event is published for `org_id`: its endpoint exists."""
        org = str(org_id)
        if not self._url or event_type not in AUDIT_CHANNELS or org in self._ready:
            return
        try:
            await self._make(org)
        except Exception as exc:  # never in the way of the event itself
            logger.warning(
                "gooclaim_audit_endpoint_not_ready org=%s error_type=%s code=%s",
                org,
                type(exc).__name__,
                _code(exc),
            )
            return
        self._ready.add(org)

    async def _make(self, org: str) -> None:
        try:
            await self._create(org)
        except Exception as exc:
            if _code(exc) == "conflict":  # registered before: keep it current
                await self._svix.endpoint.patch(
                    org, ENDPOINT_UID, EndpointPatch(url=self._url, channels=list(AUDIT_CHANNELS))
                )
            elif _code(exc) == "not_found":  # the tenant's Svix app does not exist yet
                await self._create_app(org)
                await self._create(org)
            else:
                raise

    async def _create(self, org: str) -> None:
        await self._svix.endpoint.create(
            org,
            EndpointIn(
                url=self._url,
                uid=ENDPOINT_UID,
                channels=list(AUDIT_CHANNELS),
                secret=self._secret,
                description="Gooclaim audit ledger",
            ),
        )

    async def _create_app(self, org: str) -> None:
        try:
            await self._svix.application.create(ApplicationIn(name=org, uid=org))
        except Exception as exc:
            if _code(exc) != "conflict":  # made meanwhile by another publish: fine
                raise


__all__ = ["AUDIT_CHANNELS", "ENDPOINT_UID", "AuditEndpoint"]
