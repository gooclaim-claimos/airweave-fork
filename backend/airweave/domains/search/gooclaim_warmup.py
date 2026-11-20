"""Gooclaim (2026-11-20): wake the search index when the backend starts.

Vespa's query path runs on Java, and its first queries after a start are slow. Measured on
dev right after a Vespa restart: the first keyword query 0.78 s, then 0.08 s; the first
meaning query about 1 s more. Every box start (each morning) and every deploy made the
first member's search the slow one — slow enough that it failed. Vespa's own guidance is
to run queries at startup (docs.vespa.ai, "Container tuning").

So once the backend is up, this sends a few keyword and meaning queries to Vespa in the
background, retrying while Vespa is itself still starting (~2 min after a box start).
Measured: after it, the first real keyword query took 0.27 s (was 0.78 s) and the first
meaning query 0.27 s (was ~1 s).

No tenant's data and no AI call:
- every query is limited to a collection id that no collection has, so nothing matches
  and nothing is read (an empty list would be the same: the query builder fails closed);
- the meaning query uses a fixed unit vector of the deployment's size, not an embedding.

Never raises: a warm-up that cannot run leaves search exactly as it was.
"""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from typing import TYPE_CHECKING

from airweave.domains.embedders.types import DenseEmbedding
from airweave.domains.search.types import QueryEmbeddings, SearchPlan, SearchQuery

if TYPE_CHECKING:
    from airweave.domains.embedders.protocols import SparseEmbedderProtocol
    from airweave.domains.search.adapters.vector_db.protocol import VectorDBProtocol

logger = logging.getLogger(__name__)

#: How many times each kind of query is sent once Vespa answers (more JIT, still cheap).
ROUNDS = 3
#: How long to keep trying while Vespa itself starts (it took ~2 min after a box start).
WAIT_FOR_VESPA_S = 300.0
RETRY_EVERY_S = 5.0
_WORDS = "room rent limit"


class SearchWarmup:
    """Sends match-nothing keyword and meaning queries to Vespa at startup."""

    def __init__(
        self,
        *,
        vector_db: VectorDBProtocol,
        sparse_embedder: SparseEmbedderProtocol,
        dimensions: int,
    ) -> None:
        """Wire the Vespa client, the local keyword embedder and the vector size."""
        self._vector_db = vector_db
        self._sparse = sparse_embedder
        self._dimensions = dimensions

    def _unit_vector(self) -> list[float]:
        """The placeholder meaning vector: unit length, the deployment's size.

        Built when the warm-up runs, never at wiring time: a bad size fails the warm-up
        (quietly), never the backend's start.
        """
        return [1 / math.sqrt(self._dimensions)] * self._dimensions

    async def _query(self, strategy: str) -> None:
        plan = SearchPlan(
            query=SearchQuery(primary=_WORDS), limit=8, offset=0, retrieval_strategy=strategy
        )
        dense = [DenseEmbedding(vector=self._unit_vector())] if strategy == "hybrid" else None
        embeddings = QueryEmbeddings(
            dense_embeddings=dense,
            sparse_embedding=await self._sparse.embed(_WORDS),
        )
        compiled = await self._vector_db.compile_query(
            plan=plan, embeddings=embeddings, collection_ids=[str(uuid.uuid4())]
        )
        await self._vector_db.execute_query(compiled)

    async def run(
        self, *, wait_for_vespa_s: float = WAIT_FOR_VESPA_S, retry_every_s: float = RETRY_EVERY_S
    ) -> bool:
        """True once Vespa answered every warm-up query; False if it never did in time."""
        loop = asyncio.get_running_loop()
        give_up_at = loop.time() + wait_for_vespa_s
        while True:
            try:
                started = loop.time()
                for _ in range(ROUNDS):
                    await self._query("keyword")
                    await self._query("hybrid")
                logger.info("search_warmup_done ms=%d", int((loop.time() - started) * 1000))
                return True
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # Vespa still starting, or down — try again later
                if loop.time() >= give_up_at:
                    logger.warning("search_warmup_gave_up error_type=%s", type(exc).__name__)
                    return False
                await asyncio.sleep(retry_every_s)


__all__ = ["ROUNDS", "SearchWarmup"]
