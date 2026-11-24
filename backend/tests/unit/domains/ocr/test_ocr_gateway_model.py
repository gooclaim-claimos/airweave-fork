"""Gooclaim (T542): through the gateway, OCR sends the TASK name from OCR_GATEWAY_MODEL.

The gateway key maps the task (`knowledge.read`) to the real OCR model, set in the
Console. Without the setting it sends the real model, as before.
"""

import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from airweave.domains.ocr.mistral.ocr_client import MistralOcrClient


async def _sent_model(monkeypatch: pytest.MonkeyPatch, task: str | None) -> str:
    monkeypatch.setenv("LLM_GATEWAY_URL", "http://gateway:4000/")
    monkeypatch.setenv("LLM_GATEWAY_API_KEY", "sk-test")
    if task is None:
        monkeypatch.delenv("OCR_GATEWAY_MODEL", raising=False)
    else:
        monkeypatch.setenv("OCR_GATEWAY_MODEL", task)
    client = MistralOcrClient()
    client.ensure_initialized()
    answer = MagicMock()
    answer.json.return_value = {"pages": [{"markdown": "ok"}]}
    client._client = MagicMock(post=AsyncMock(return_value=answer))
    chunk = types.SimpleNamespace(extension=".pdf", is_image=False)
    await client._ocr_via_gateway(chunk, b"%PDF-1.4")
    url = client._client.post.call_args.args[0]
    assert url == "http://gateway:4000/v1/ocr"
    return client._client.post.call_args.kwargs["json"]["model"]


@pytest.mark.asyncio
async def test_the_gateway_is_sent_the_task_name(monkeypatch: pytest.MonkeyPatch) -> None:
    assert await _sent_model(monkeypatch, "knowledge.read") == "knowledge.read"


@pytest.mark.asyncio
async def test_without_the_setting_the_real_model_is_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    assert await _sent_model(monkeypatch, None) == "mistral-ocr-latest"
