"""Gooclaim fork (T420): classic search is built with the relevance gate.

Classic search answers questions, so it must be able to return nothing. The
gate is wired when the LLM gateway is configured; agentic search keeps its own
reranker; without a gateway, classic keeps upstream behaviour.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from airweave.adapters.reranker.relevance_gate import GatewayRelevanceGate
from airweave.core.container import factory


def _services(monkeypatch: pytest.MonkeyPatch, *, gateway: bool) -> dict:
    if gateway:
        monkeypatch.setenv("LLM_GATEWAY_URL", "http://litellm.test:4000")
        monkeypatch.setenv("LLM_GATEWAY_API_KEY", "fake-gateway-key")
    else:
        monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
        monkeypatch.delenv("LLM_GATEWAY_API_KEY", raising=False)
    monkeypatch.setattr(factory, "_build_llm_chain", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr("vespa.application.Vespa", MagicMock())
    settings = MagicMock()
    settings.COHERE_API_KEY = None
    return factory._create_search_services(
        settings=settings,
        circuit_breaker=MagicMock(),
        dense_embedder=MagicMock(),
        sparse_embedder=MagicMock(),
        collection_repo=MagicMock(),
        sc_repo=MagicMock(),
        source_registry=MagicMock(),
        entity_definition_registry=MagicMock(),
        event_bus=MagicMock(),
        source_lifecycle=MagicMock(),
        access_broker=MagicMock(),
    )


def test_classic_search_gets_the_gate_when_the_gateway_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(monkeypatch, gateway=True)
    gate = services["classic_search"]._reranker
    assert isinstance(gate, GatewayRelevanceGate)
    assert gate._url == "http://litellm.test:4000/v1/chat/completions"
    assert gate._model == "fast"
    assert services["agentic_search"]._reranker is None


def test_without_a_gateway_classic_search_keeps_upstream_behaviour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(monkeypatch, gateway=False)
    assert services["classic_search"]._reranker is None
