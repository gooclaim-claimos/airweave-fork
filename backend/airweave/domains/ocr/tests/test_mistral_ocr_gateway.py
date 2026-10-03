"""Gooclaim (T418) — Mistral OCR through the LLM gateway.

Every AI call goes through the gateway and a provider key lives only there, so
with LLM_GATEWAY_URL set the client needs no MISTRAL_API_KEY: one POST to the
gateway's /v1/ocr with the document inline, billed to the tenant it was read for.
"""

import base64
import json
from unittest.mock import patch

import httpx
import pytest

from airweave.core.gateway_tenant import set_gateway_tenant
from airweave.domains.ocr.mistral.models import FileChunk
from airweave.domains.ocr.mistral.ocr_client import MistralOcrClient
from airweave.domains.sync_pipeline.exceptions import SyncFailureError

TENANT = "0e2b24f0-e6e3-4161-be0f-5a8164aa01a5"


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setenv("LLM_GATEWAY_URL", "http://gateway:4000/")
    monkeypatch.setenv("LLM_GATEWAY_API_KEY", "sk-gateway")
    set_gateway_tenant(TENANT)
    yield
    set_gateway_tenant(None)


def _wired_client() -> tuple[MistralOcrClient, list[httpx.Request]]:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(
            200,
            json={
                "pages": [
                    {"index": 0, "markdown": "# Bill"},
                    {"index": 1, "markdown": "Total 1200"},
                ]
            },
        )

    with patch("airweave.domains.ocr.mistral.ocr_client.settings") as mock_settings:
        mock_settings.MISTRAL_API_KEY = None  # the gateway mode must not need it
        client = MistralOcrClient()
        client.ensure_initialized()
    client._client._transport = httpx.MockTransport(handler)
    client._rate_limiter.acquire = _no_wait  # type: ignore[method-assign]
    return client, sent


async def _no_wait() -> None:
    return None


def _chunk(tmp_path, name: str, content: bytes) -> FileChunk:
    path = tmp_path / name
    path.write_bytes(content)
    return FileChunk(original_path=str(path), chunk_path=str(path), batch_index=0)


@pytest.mark.asyncio
async def test_a_pdf_is_read_through_the_gateway_inline_and_billed_to_its_tenant(gateway, tmp_path):
    client, sent = _wired_client()

    result = await client.ocr_chunk(_chunk(tmp_path, "bill.pdf", b"%PDF-1.4 fake"))

    assert result.markdown == "# Bill\n\nTotal 1200"
    assert len(sent) == 1, "no upload and no delete — one OCR call"
    request = sent[0]
    assert str(request.url) == "http://gateway:4000/v1/ocr"
    assert request.headers["authorization"] == "Bearer sk-gateway"
    assert request.headers["x-litellm-customer-id"] == TENANT
    body = json.loads(request.content)
    assert body["model"] == "mistral-ocr-latest"
    expected = "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4 fake").decode()
    assert body["document"] == {"type": "document_url", "document_url": expected}


@pytest.mark.asyncio
async def test_an_image_goes_as_an_image_url(gateway, tmp_path):
    client, sent = _wired_client()
    await client.ocr_chunk(_chunk(tmp_path, "scan.png", b"\x89PNG fake"))
    document = json.loads(sent[0].content)["document"]
    assert document["type"] == "image_url"
    assert document["image_url"].startswith("data:image/png;base64,")


def test_a_gateway_without_its_key_fails_loudly(monkeypatch):
    monkeypatch.setenv("LLM_GATEWAY_URL", "http://gateway:4000")
    monkeypatch.delenv("LLM_GATEWAY_API_KEY", raising=False)
    with pytest.raises(SyncFailureError, match="LLM_GATEWAY_API_KEY"):
        MistralOcrClient().ensure_initialized()


def test_without_a_gateway_the_mistral_key_is_still_required(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    with patch("airweave.domains.ocr.mistral.ocr_client.settings") as mock_settings:
        mock_settings.MISTRAL_API_KEY = None
        with pytest.raises(SyncFailureError, match="MISTRAL_API_KEY"):
            MistralOcrClient().ensure_initialized()
