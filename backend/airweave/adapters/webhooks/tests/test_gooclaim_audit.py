"""Gooclaim: every tenant's data-sources events reach the audit ledger.

Found 2026-11-20: no Svix endpoint was registered for any tenant, so the ledger never got one.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest
from svix.exceptions import HttpError as SvixHttpError

from airweave.adapters.webhooks.gooclaim_audit import AUDIT_CHANNELS, ENDPOINT_UID, AuditEndpoint
from airweave.adapters.webhooks.svix import SvixAdapter
from airweave.core.events.sync import SyncLifecycleEvent

URL = "http://172.31.35.3:8000/v1/audit/airweave-webhook"
SECRET = "whsec_dGVzdHNlY3JldGZvcndlYmhvb2tzaWduYXR1cmU="


def _svix() -> MagicMock:
    svix = MagicMock()
    svix.endpoint.create = AsyncMock()
    svix.endpoint.patch = AsyncMock()
    svix.application.create = AsyncMock()
    svix.message.create = AsyncMock(return_value=MagicMock(id="msg_1", channels=["sync.completed"]))
    svix.message.list = AsyncMock(return_value=MagicMock(data=[]))
    return svix


def _error(code: str) -> SvixHttpError:
    err = SvixHttpError.__new__(SvixHttpError)
    err.code, err.detail, err.status_code, err.args = code, code, 409, (code,)
    return err


@pytest.mark.asyncio
async def test_no_address_means_nothing_is_registered() -> None:
    svix = _svix()
    await AuditEndpoint(svix, "", SECRET).ensure(uuid4(), "sync.completed")
    svix.endpoint.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_one_endpoint_per_tenant_on_the_four_channels_made_once() -> None:
    svix, org, other = _svix(), uuid4(), uuid4()
    audit = AuditEndpoint(svix, URL, SECRET)

    await audit.ensure(org, "sync.completed")
    await audit.ensure(org, "source_connection.created")  # same tenant: not again
    await audit.ensure(other, "sync.failed")  # a new tenant gets its own

    assert svix.endpoint.create.await_count == 2
    app_id, endpoint = svix.endpoint.create.await_args_list[0].args
    assert app_id == str(org)
    assert endpoint.url == URL and endpoint.uid == ENDPOINT_UID and endpoint.secret == SECRET
    assert endpoint.channels == list(AUDIT_CHANNELS)


@pytest.mark.asyncio
async def test_events_the_ledger_does_not_take_register_nothing() -> None:
    svix = _svix()
    audit = AuditEndpoint(svix, URL, SECRET)
    for event_type in ("search.completed", "collection.created", "sync.running"):
        await audit.ensure(uuid4(), event_type)
    svix.endpoint.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_endpoint_registered_before_is_brought_up_to_date() -> None:
    svix, org = _svix(), uuid4()
    svix.endpoint.create.side_effect = _error("conflict")
    await AuditEndpoint(svix, URL, SECRET).ensure(org, "sync.completed")
    app_id, uid, patch = svix.endpoint.patch.await_args.args
    assert (app_id, uid) == (str(org), ENDPOINT_UID)
    assert patch.url == URL and patch.channels == list(AUDIT_CHANNELS)


@pytest.mark.asyncio
async def test_a_tenant_with_no_svix_app_yet_gets_one_then_the_endpoint() -> None:
    svix, org = _svix(), uuid4()
    svix.endpoint.create.side_effect = [_error("not_found"), None]
    await AuditEndpoint(svix, URL, SECRET).ensure(org, "sync.completed")
    svix.application.create.assert_awaited_once()
    assert svix.endpoint.create.await_count == 2


@pytest.mark.asyncio
async def test_svix_down_is_logged_never_raised_and_tried_again_next_time() -> None:
    svix, org = _svix(), uuid4()
    svix.endpoint.create.side_effect = [ConnectionError("svix down"), None]
    audit = AuditEndpoint(svix, URL, SECRET)
    await audit.ensure(org, "sync.completed")  # does not raise
    await audit.ensure(org, "sync.completed")  # not marked ready: tried again
    assert svix.endpoint.create.await_count == 2


@pytest.mark.asyncio
async def test_the_endpoint_exists_before_the_first_event_is_published() -> None:
    """The audit endpoint is made before the message.

    Svix delivers a message to the endpoints that exist when it is created — the first
    sync of a new tenant must reach the ledger too.
    """
    with patch.object(SvixAdapter, "__init__", lambda self: None):
        adapter = SvixAdapter()
    svix = _svix()
    order = MagicMock()
    svix.endpoint.create = AsyncMock(side_effect=lambda *a, **k: order.endpoint())
    svix.message.create = AsyncMock(
        side_effect=lambda *a, **k: order.message() or MagicMock(id="m", channels=[])
    )
    adapter._svix = svix
    adapter._audit = AuditEndpoint(svix, URL, SECRET)
    org = uuid4()
    event = SyncLifecycleEvent.completed(
        organization_id=org,
        sync_id=uuid4(),
        sync_job_id=uuid4(),
        collection_id=uuid4(),
        source_connection_id=uuid4(),
        source_type="gooclaim_upload",
        collection_name="Policy wordings",
        collection_readable_id="policy-wordings",
    )
    await adapter.publish_event(event)
    assert order.mock_calls[:2] == [call.endpoint(), call.message()]
