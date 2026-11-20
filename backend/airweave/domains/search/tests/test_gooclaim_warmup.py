"""Gooclaim: the startup warm-up wakes Vespa without reading data or calling an AI."""

from __future__ import annotations

import math
import uuid
from typing import Any

import pytest

from airweave.domains.embedders.types import SparseEmbedding
from airweave.domains.search.gooclaim_warmup import ROUNDS, SearchWarmup


class _Sparse:
    async def embed(self, text: str) -> SparseEmbedding:
        return SparseEmbedding(indices=[1, 2], values=[0.5, 0.5])


class _Vespa:
    """Records what would be sent; fails the first `down` executions (Vespa starting)."""

    def __init__(self, down: int = 0) -> None:
        self.down = down
        self.compiled: list[dict[str, Any]] = []
        self.executed = 0

    async def compile_query(self, *, plan: Any, embeddings: Any, collection_ids: list[str]) -> Any:
        self.compiled.append(
            {
                "strategy": str(plan.retrieval_strategy.value),
                "embeddings": embeddings,
                "collection_ids": collection_ids,
            }
        )
        return object()

    async def execute_query(self, compiled: Any) -> Any:
        if self.down > 0:
            self.down -= 1
            raise ConnectionError("vespa starting")
        self.executed += 1
        return object()


def _warmup(vespa: _Vespa, dims: int = 8) -> SearchWarmup:
    return SearchWarmup(vector_db=vespa, sparse_embedder=_Sparse(), dimensions=dims)


@pytest.mark.asyncio
async def test_keyword_and_meaning_queries_that_match_nothing_and_call_no_ai() -> None:
    vespa = _Vespa()
    assert await _warmup(vespa, dims=1536).run() is True

    assert vespa.executed == 2 * ROUNDS
    assert {c["strategy"] for c in vespa.compiled} == {"keyword", "hybrid"}
    for call in vespa.compiled:
        # One collection id no collection has — nothing matches, nothing is read.
        (cid,) = call["collection_ids"]
        uuid.UUID(cid)
        dense = call["embeddings"].dense_embeddings
        if call["strategy"] == "hybrid":
            # A fixed unit vector of the deployment's size — not an embedding call.
            (vector,) = dense
            assert len(vector.vector) == 1536
            assert math.isclose(math.sqrt(sum(v * v for v in vector.vector)), 1.0)
        else:
            assert dense is None


@pytest.mark.asyncio
async def test_it_waits_while_vespa_is_still_starting() -> None:
    vespa = _Vespa(down=3)
    assert await _warmup(vespa).run(wait_for_vespa_s=5, retry_every_s=0) is True
    assert vespa.executed == 2 * ROUNDS


@pytest.mark.asyncio
async def test_vespa_never_up_gives_up_quietly_never_raises() -> None:
    vespa = _Vespa(down=10_000)
    assert await _warmup(vespa).run(wait_for_vespa_s=0, retry_every_s=0) is False
    assert vespa.executed == 0
