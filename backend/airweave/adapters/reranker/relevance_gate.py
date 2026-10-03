"""Gooclaim fork (T420) — keep only passages that help answer the question.

Classic search returned the collection's top results for ANY query: Vespa's
nearest-neighbour search hands back the nearest thing even when nothing
matches, and the hybrid score is min-max normalised inside each result set, so
the best of a set of bad hits still scores ~2.0. "What is the capital of
France?" against an IRDA circular came back with three results. Downstream,
the data-sources tool tells the Kernel that an empty result is a real answer —
"say so and offer a human" — and that could never happen.

No absolute score exists to cut on (see ``vespa/app/schemas/base_entity.sd``),
and Cohere — the only reranker upstream ships — is a provider key no service
may hold here. So a small model behind the LLM gateway grades each passage:

    3  states the answer, or the rule that decides it
    2  holds facts needed for part of the answer
    1  same subject, nothing that answers this question
    0  unrelated, or only names / titles / metadata

and the gate keeps grades 2 and 3. Zero kept is an empty result — the honest
"not in your documents".

Through the gateway with the tenant named (``tenant_event_hooks``), like every
other AI call in this fork. A failure RAISES: classic search then fails and the
caller sees an outage, which is true — returning the ungated results would
quietly bring back the answers this exists to stop.

Never logs the query or a passage: a member's question can carry PHI.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from airweave.adapters.reranker.exceptions import RerankerError
from airweave.adapters.reranker.types import RerankerResult
from airweave.core.gateway_tenant import tenant_event_hooks
from airweave.core.logging import logger
from airweave.core.protocols.reranker import RerankerProtocol

#: The gateway alias it asks. Grading is a small judgement made on every
#: search; the `smart` alias would cost roughly a hundred times more per call.
RELEVANCE_MODEL = "fast"

#: Grades kept. 1 is "same subject" — the near-miss a member must not be answered from.
KEEP_AT_OR_ABOVE = 2
MAX_GRADE = 3

#: The chunker's hard ceiling is 8192 tokens (~32k characters), so this never
#: cuts a real chunk; it only bounds a malformed one.
MAX_CHARS_PER_PASSAGE = 32_000

_TIMEOUT_SECONDS = 60.0

SYSTEM_PROMPT = """You decide which retrieved passages can help answer a question put to a \
health-insurance claims assistant. The passages come from the insurer's or TPA's own \
documents: policy wordings, regulations, circulars, internal notes.

Give every passage exactly one grade:
3 = states the answer, or the rule that decides it.
2 = contains facts needed for part of the answer.
1 = same subject, but nothing that helps answer THIS question.
0 = unrelated, or only names, titles, file names or metadata with no substance.

Judge only from the passage text, never from what you know. The question may be in \
English, Hindi or Hinglish and the passages in another language: judge meaning, not \
shared words. Answer with an object mapping every passage number you were given to its \
grade, e.g. {"0": 3, "1": 0}."""


def _response_format(count: int) -> dict[str, Any]:
    """A schema with ONE required key per passage, built for this call.

    A list of {index, grade} let the model skip a passage — seen live: two
    passages in, one grade back — and a skipped passage is dropped, so an
    answer could vanish. Strict mode cannot leave out a required key.
    """
    keys = [str(i) for i in range(count)]
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "passage_grades",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {k: {"type": "integer", "enum": [0, 1, 2, 3]} for k in keys},
                "required": keys,
                "additionalProperties": False,
            },
        },
    }


def _chat_url(gateway_url: str) -> str:
    base = gateway_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return f"{base}/v1/chat/completions"


def _user_prompt(query: str, documents: list[str]) -> str:
    passages = "\n\n".join(
        f"[{i}]\n{doc[:MAX_CHARS_PER_PASSAGE]}" for i, doc in enumerate(documents)
    )
    return f"Question: {query}\n\nPassages:\n\n{passages}"


def _parse_grades(body: dict[str, Any], count: int) -> dict[int, int]:
    """Map each passage index to its grade, trusting nothing the model got wrong.

    A missing or impossible grade leaves that passage out (dropped); a key that
    names no passage is ignored. The schema makes a missing key a provider fault,
    not a model choice — it is still not trusted.
    """
    try:
        content = body["choices"][0]["message"]["content"]
        data = json.loads(content)
        if not isinstance(data, dict):
            raise TypeError("not an object")
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise RerankerError(f"relevance gate: unreadable model reply ({type(e).__name__})") from e
    grades: dict[int, int] = {}
    for i in range(count):
        grade = data.get(str(i))
        if isinstance(grade, int) and 0 <= grade <= MAX_GRADE:
            grades[i] = grade
    return grades


class GatewayRelevanceGate(RerankerProtocol):
    """A reranker that may return FEWER results than it was given — even none."""

    def __init__(
        self,
        gateway_url: str,
        api_key: str,
        *,
        model: str = RELEVANCE_MODEL,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Talk to the gateway at ``gateway_url`` with the service's gateway key."""
        self._url = _chat_url(gateway_url)
        self._api_key = api_key
        self._model = model
        self._client = http_client or httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS, event_hooks=tenant_event_hooks()
        )

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankerResult]:
        """Grade every passage; return the ones graded 2 or 3, best first."""
        if not documents:
            return []
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(query, documents)},
            ],
            "response_format": _response_format(len(documents)),
            "reasoning_effort": "minimal",
        }
        try:
            response = await self._client.post(
                self._url,
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.HTTPError as e:
            raise RerankerError(f"relevance gate: gateway unreachable ({type(e).__name__})") from e
        if response.status_code >= 400:
            raise RerankerError(f"relevance gate: gateway answered {response.status_code}")
        try:
            body = response.json()
        except ValueError as e:
            raise RerankerError("relevance gate: gateway reply is not JSON") from e

        grades = _parse_grades(body, len(documents))
        kept = sorted(
            (i for i, g in grades.items() if g >= KEEP_AT_OR_ABOVE),
            key=lambda i: (-grades[i], i),
        )
        if top_n is not None:
            kept = kept[:top_n]
        logger.info(
            f"[RelevanceGate] kept={len(kept)} of={len(documents)} graded={len(grades)} "
            f"grades={sorted(grades.values(), reverse=True)}"
        )
        return [RerankerResult(index=i, relevance_score=grades[i] / MAX_GRADE) for i in kept]
