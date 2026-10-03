"""Gooclaim fork (T420): the relevance gate keeps only passages that answer — or none.

Read at the wire: every test records the request the gate actually sends to the
gateway, and answers it the way LiteLLM's chat-completions endpoint does.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from airweave.adapters.reranker import relevance_gate as gate_mod
from airweave.adapters.reranker.exceptions import RerankerError
from airweave.adapters.reranker.relevance_gate import (
    MAX_CHARS_PER_PASSAGE,
    GatewayRelevanceGate,
)
from airweave.core.gateway_tenant import GATEWAY_CUSTOMER_HEADER, set_gateway_tenant

GATEWAY = "http://litellm.test:4000"
KEY = "fake-gateway-key"
TENANT = "0e2b24f0-e6e3-4161-be0f-5a8164aa01a5"
QUESTION = "will my health insurance claim pay for a lumbo sacral belt?"
DOCS = [
    "# Metadata\n**Name**: Native Upload — irdaitest",
    "150 | LUMBO SACRAL BELT | Essential and should be paid for lumbar spine surgery.",
    "151 | NIMBUS BED | Payable for ICU patients needing more than 3 days.",
]


def _reply(grades: list[dict[str, Any]] | Any, status: int = 200) -> httpx.Response:
    content = json.dumps({"grades": grades}) if isinstance(grades, list) else grades
    return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})


class _Wire:
    """Records every request; answers with the next queued response."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.requests: list[httpx.Request] = []
        self._responses = list(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

    def body(self, i: int = 0) -> dict[str, Any]:
        return json.loads(self.requests[i].content)


def _gate(wire: _Wire, url: str = GATEWAY) -> GatewayRelevanceGate:
    return GatewayRelevanceGate(url, KEY, http_client=wire.client())


@pytest.mark.asyncio
async def test_it_asks_the_gateway_with_the_service_key_and_the_fast_alias() -> None:
    wire = _Wire(_reply([{"index": 1, "grade": 3}]))
    await _gate(wire).rerank(QUESTION, DOCS)

    req = wire.requests[0]
    assert str(req.url) == f"{GATEWAY}/v1/chat/completions"
    assert req.headers["Authorization"] == f"Bearer {KEY}"
    body = wire.body()
    assert body["model"] == "fast"
    assert body["response_format"]["type"] == "json_schema"
    user = body["messages"][1]["content"]
    assert QUESTION in user
    for i, doc in enumerate(DOCS):
        assert f"[{i}]\n{doc}" in user


@pytest.mark.parametrize("url", [GATEWAY + "/", GATEWAY + "/v1", GATEWAY + "/v1/"])
@pytest.mark.asyncio
async def test_a_gateway_url_with_or_without_v1_reaches_the_same_endpoint(url: str) -> None:
    wire = _Wire(_reply([]))
    await _gate(wire, url).rerank(QUESTION, DOCS)
    assert str(wire.requests[0].url) == f"{GATEWAY}/v1/chat/completions"


@pytest.mark.asyncio
async def test_the_call_is_billed_to_the_tenant_of_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default client carries the tenant hook — the same one embeddings and OCR use."""
    wire = _Wire(_reply([]))
    real = httpx.AsyncClient

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return real(*args, transport=httpx.MockTransport(wire.handler), **kwargs)

    monkeypatch.setattr(gate_mod.httpx, "AsyncClient", client)
    set_gateway_tenant(TENANT)
    try:
        await GatewayRelevanceGate(GATEWAY, KEY).rerank(QUESTION, DOCS)
    finally:
        set_gateway_tenant(None)
    assert wire.requests[0].headers[GATEWAY_CUSTOMER_HEADER] == TENANT


@pytest.mark.asyncio
async def test_only_passages_that_answer_are_kept_best_first() -> None:
    wire = _Wire(
        _reply(
            [
                {"index": 0, "grade": 0},
                {"index": 1, "grade": 2},
                {"index": 2, "grade": 3},
            ]
        )
    )
    out = await _gate(wire).rerank(QUESTION, DOCS)
    assert [(r.index, r.relevance_score) for r in out] == [(2, 1.0), (1, 2 / 3)]


@pytest.mark.asyncio
async def test_equal_grades_keep_the_retrieval_order() -> None:
    wire = _Wire(_reply([{"index": 2, "grade": 3}, {"index": 1, "grade": 3}]))
    out = await _gate(wire).rerank(QUESTION, DOCS)
    assert [r.index for r in out] == [1, 2]


@pytest.mark.asyncio
async def test_same_subject_is_not_an_answer() -> None:
    """Grade 1 is not an answer.

    "Same subject, nothing that answers" is the near miss a member must not be
    answered from.
    """
    wire = _Wire(_reply([{"index": 1, "grade": 1}, {"index": 2, "grade": 1}]))
    assert await _gate(wire).rerank(QUESTION, DOCS) == []


@pytest.mark.asyncio
async def test_nothing_relevant_is_an_empty_result() -> None:
    """The whole point: "What is the capital of France?" must come back empty."""
    wire = _Wire(_reply([{"index": i, "grade": 0} for i in range(3)]))
    assert await _gate(wire).rerank("What is the capital of France?", DOCS) == []


@pytest.mark.asyncio
async def test_top_n_caps_what_is_kept() -> None:
    wire = _Wire(_reply([{"index": i, "grade": 3} for i in range(3)]))
    assert [r.index for r in await _gate(wire).rerank(QUESTION, DOCS, top_n=2)] == [0, 1]


@pytest.mark.asyncio
async def test_a_reply_the_model_got_wrong_is_not_trusted() -> None:
    """Skipped index → dropped.

    Repeated index → the first grade. Invented index or impossible grade → ignored.
    """
    wire = _Wire(
        _reply(
            [
                {"index": 1, "grade": 3},
                {"index": 1, "grade": 0},
                {"index": 7, "grade": 3},
                {"index": 2, "grade": 9},
                {"index": "0", "grade": 3},
            ]
        )
    )
    assert [r.index for r in await _gate(wire).rerank(QUESTION, DOCS)] == [1]


@pytest.mark.asyncio
async def test_no_passages_means_no_call() -> None:
    wire = _Wire()
    assert await _gate(wire).rerank(QUESTION, []) == []
    assert wire.requests == []


@pytest.mark.asyncio
async def test_a_runaway_passage_is_bounded_and_a_real_chunk_is_not() -> None:
    real_chunk = "x" * 30_000  # the chunker's 8192-token ceiling is ~32k characters
    runaway = "y" * (MAX_CHARS_PER_PASSAGE + 500)
    wire = _Wire(_reply([]))
    await _gate(wire).rerank(QUESTION, [real_chunk, runaway])
    user = wire.body()["messages"][1]["content"]
    assert real_chunk in user
    assert "y" * MAX_CHARS_PER_PASSAGE in user
    assert "y" * (MAX_CHARS_PER_PASSAGE + 1) not in user


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(429, json={"error": "budget"}),
        httpx.Response(500, text="boom"),
        httpx.Response(200, text="not json"),
        _reply("this is not the schema"),
        httpx.Response(200, json={"choices": []}),
        httpx.ConnectError("refused"),
    ],
)
@pytest.mark.asyncio
async def test_a_gate_that_cannot_decide_fails_loudly(failure: Any) -> None:
    """A gate that cannot decide fails loudly.

    Returning the ungated results would quietly bring back the answers this
    exists to stop — the caller must see an outage instead.
    """
    wire = _Wire(failure)
    with pytest.raises(RerankerError):
        await _gate(wire).rerank(QUESTION, DOCS)


@pytest.mark.asyncio
async def test_neither_the_question_nor_a_passage_reaches_the_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A member's question can carry PHI."""
    lines: list[str] = []
    monkeypatch.setattr(gate_mod.logger, "info", lambda msg, *_a, **_k: lines.append(str(msg)))
    wire = _Wire(_reply([{"index": 1, "grade": 3}]))
    await _gate(wire).rerank(QUESTION, DOCS)
    assert lines, "the gate should say what it kept"
    logged = "\n".join(lines)
    assert "lumbo" not in logged.lower()
    assert "LUMBO" not in logged
