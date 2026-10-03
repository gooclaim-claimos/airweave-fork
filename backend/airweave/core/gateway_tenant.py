"""Gooclaim fork — name the tenant on every AI call that goes through the LLM gateway.

The gateway (LiteLLM) bills a call to a customer and enforces that customer's
budget from the ``x-litellm-customer-id`` header, which it reads before anything
else. Without it every embedding, search answer and OCR page Airweave runs is
spend that belongs to no tenant.

Why a ContextVar and not an argument: the dense embedder, the search LLM and the
OCR provider are built ONCE at startup and their methods carry no organization
(``embed_many(texts)``, ``structured_output(...)``, ``convert_batch(...)``).
Passing the tenant as an argument would mean re-plumbing every protocol, every
implementation and every fake in an upstream codebase we rebase. Instead the
organization is held here for the duration of an API request (``get_context``)
or a sync (``SyncContextBuilder.build``), and an httpx request hook on the AI
clients copies it into the header. Tasks spawned from there inherit it —
``asyncio`` copies the context when a task is created.

The Airweave organization id IS the Gooclaim tenant id (orgs are auto-provisioned
with the tenant's UUID — ``api/context_resolver.py``), so nothing is mapped.

Unset — a startup probe, a script — means no header: the call is billed to the
gateway key alone, never to a guessed tenant.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Awaitable, Callable
from uuid import UUID

import httpx

GATEWAY_CUSTOMER_HEADER = "x-litellm-customer-id"

_organization_id: ContextVar[str | None] = ContextVar(
    "gateway_tenant_organization_id", default=None
)


def set_gateway_tenant(organization_id: UUID | str | None) -> None:
    """Bill the AI calls of the current request / sync to this organization."""
    _organization_id.set(str(organization_id) if organization_id else None)


def current_gateway_tenant() -> str | None:
    """The organization the next AI call will be billed to, if any."""
    return _organization_id.get()


async def _name_the_tenant(request: httpx.Request) -> None:
    organization_id = _organization_id.get()
    if organization_id:
        request.headers[GATEWAY_CUSTOMER_HEADER] = organization_id


def tenant_event_hooks() -> dict[str, list[Callable[[httpx.Request], Awaitable[Any]]]]:
    """Return httpx ``event_hooks`` that put the current tenant on every request.

    Attach them ONLY to a client whose base URL is the gateway — the header
    names a tenant, and a provider called directly has no business seeing it.
    """
    return {"request": [_name_the_tenant]}
