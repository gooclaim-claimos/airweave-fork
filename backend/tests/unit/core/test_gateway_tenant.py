"""Gooclaim (T418) — every AI call through the gateway names its tenant.

The gateway (LiteLLM) bills a call to the customer in `x-litellm-customer-id` and
refuses one past that customer's budget. These pin the two places that decide the
tenant (an API request, a sync) and the hook that puts it on the wire.
"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from airweave.api import deps
from airweave.core.gateway_tenant import (
    GATEWAY_CUSTOMER_HEADER,
    current_gateway_tenant,
    set_gateway_tenant,
    tenant_event_hooks,
)
from airweave.domains.sync_pipeline.builders import sync as builder_mod

ORG_A = uuid.UUID("0e2b24f0-e6e3-4161-be0f-5a8164aa01a5")
ORG_B = uuid.UUID("78e7553e-c7a7-4598-9fd1-6f12759cd219")


@pytest.fixture(autouse=True)
def _no_tenant():
    set_gateway_tenant(None)
    yield
    set_gateway_tenant(None)


async def _send_through_hooks() -> httpx.Request:
    request = httpx.Request("POST", "http://gateway:4000/v1/embeddings")
    for hook in tenant_event_hooks()["request"]:
        await hook(request)
    return request


# ── the hook ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_call_names_the_tenant_it_was_made_for():
    set_gateway_tenant(ORG_A)
    request = await _send_through_hooks()
    assert request.headers[GATEWAY_CUSTOMER_HEADER] == str(ORG_A)


@pytest.mark.asyncio
async def test_no_tenant_means_no_header_never_a_guess():
    request = await _send_through_hooks()
    assert GATEWAY_CUSTOMER_HEADER not in request.headers


@pytest.mark.asyncio
async def test_a_task_spawned_by_the_request_keeps_its_tenant():
    # The sync pipeline and search fan out with create_task / gather.
    set_gateway_tenant(ORG_A)
    assert await asyncio.create_task(_read_tenant()) == str(ORG_A)
    assert await asyncio.gather(_read_tenant(), _read_tenant()) == [str(ORG_A)] * 2


async def _read_tenant() -> str | None:
    return current_gateway_tenant()


# ── where the tenant is decided: an API request ─────────────────────────────


async def _get_context_for(organization) -> None:
    ctx = SimpleNamespace(organization=organization, auth_metadata={})
    with patch.object(deps, "ContextResolver") as resolver_cls:
        resolver_cls.return_value.resolve = AsyncMock(return_value=ctx)
        await deps.get_context(
            request=MagicMock(),
            db=MagicMock(),
            x_api_key=None,
            x_organization_id=None,
            x_gck_platform_admin=None,
            x_gck_return_url=None,
            x_gck_tenant_name=None,
            x_gck_user_email=None,
            auth0_user=None,
            cache=MagicMock(),
            rate_limiter=MagicMock(),
        )


@pytest.mark.asyncio
async def test_an_api_request_bills_its_ai_calls_to_its_organization():
    await _get_context_for(SimpleNamespace(id=ORG_A))
    assert current_gateway_tenant() == str(ORG_A)


@pytest.mark.asyncio
async def test_the_next_request_on_the_same_task_never_inherits_the_last_tenant():
    # A keep-alive connection can serve two callers from one task.
    await _get_context_for(SimpleNamespace(id=ORG_A))
    await _get_context_for(SimpleNamespace(id=ORG_B))
    assert current_gateway_tenant() == str(ORG_B)
    await _get_context_for(None)
    assert current_gateway_tenant() is None


# ── where the tenant is decided: a sync ─────────────────────────────────────


@pytest.mark.asyncio
async def test_a_sync_bills_its_ai_calls_to_the_organization_it_syncs_for():
    ctx = SimpleNamespace(organization=SimpleNamespace(id=ORG_B))
    with (
        patch.object(builder_mod.SyncContextBuilder, "_build_logger", return_value=MagicMock()),
        patch.object(builder_mod, "SyncContext", MagicMock()),
    ):
        await builder_mod.SyncContextBuilder.build(
            db=MagicMock(),
            sync=MagicMock(),
            sync_job=MagicMock(),
            collection=MagicMock(),
            connection=MagicMock(),
            ctx=ctx,  # type: ignore[arg-type]
            source_connection_id=uuid.uuid4(),
            source_short_name="gooclaim_upload",
        )
    assert current_gateway_tenant() == str(ORG_B)
