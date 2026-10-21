"""Gooclaim (T487): the search provider names the tenant and labels the call.

It was the one AI client here without the gateway hook, so search answers were
spend that belonged to no tenant.
"""

from unittest.mock import MagicMock

import httpx
import pytest

from airweave.core.gateway_tenant import (
    GATEWAY_CUSTOMER_HEADER,
    GATEWAY_TAGS_HEADER,
    set_gateway_tenant,
)
from airweave.search.providers.openai import OpenAIProvider


@pytest.mark.asyncio
async def test_through_the_gateway_every_search_call_is_named_and_labelled(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://gateway:4000/v1")
    spec = MagicMock()
    spec.embedding_model = None
    provider = OpenAIProvider(api_key="k", model_spec=spec, ctx=MagicMock())
    hooks = provider.client._client.event_hooks["request"]
    set_gateway_tenant("0e2b24f0-e6e3-4161-be0f-5a8164aa01a5")
    try:
        request = httpx.Request("POST", "http://gateway:4000/v1/chat/completions")
        for hook in hooks:
            await hook(request)
    finally:
        set_gateway_tenant(None)
    assert request.headers[GATEWAY_CUSTOMER_HEADER] == "0e2b24f0-e6e3-4161-be0f-5a8164aa01a5"
    assert request.headers[GATEWAY_TAGS_HEADER] == "feature:documents"


def test_straight_to_openai_no_gateway_header_is_attached(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    spec = MagicMock()
    spec.embedding_model = None
    provider = OpenAIProvider(api_key="k", model_spec=spec, ctx=MagicMock())
    assert provider.client._client.event_hooks["request"] == []
