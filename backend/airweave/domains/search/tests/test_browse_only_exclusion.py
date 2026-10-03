"""Gooclaim fork (T420): browse-only entities never come back from ranked search.

An upload connection has no content — its text is its name. Nearest-neighbour
search returns the nearest thing even when nothing matches, so "Native Upload —
irdaitest" came back as a result for every question. It must stay in the index
(browse lists it) and out of every ranked result.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from airweave.domains.access_control.fakes.broker import FakeAccessBroker
from airweave.domains.embedders.fakes.embedder import FakeDenseEmbedder, FakeSparseEmbedder
from airweave.domains.search.adapters.vector_db.fakes.vector_db import FakeVectorDB
from airweave.domains.search.adapters.vector_db.filter_translator import FilterTranslator
from airweave.domains.search.executor import SearchPlanExecutor
from airweave.domains.search.types import (
    RetrievalStrategy,
    SearchPlan,
    SearchQuery,
    SearchResults,
)
from airweave.domains.search.types.filters import (
    FilterableField,
    FilterCondition,
    FilterGroup,
    FilterOperator,
)
from airweave.domains.source_connections.fakes.repository import FakeSourceConnectionRepository
from airweave.domains.sources.fakes.lifecycle import FakeSourceLifecycleService
from airweave.domains.sources.fakes.registry import FakeSourceRegistry
from airweave.platform.entities._base import BaseEntity, browse_only_entity_types
from airweave.platform.entities.gooclaim_upload import (
    GooclaimUploadConnectionEntity,
    GooclaimUploadFileEntity,
)

ENTITY_TYPE = FilterableField.SYSTEM_METADATA_ENTITY_TYPE


def _executor(vector_db: FakeVectorDB) -> SearchPlanExecutor:
    return SearchPlanExecutor(
        dense_embedder=FakeDenseEmbedder(),
        sparse_embedder=FakeSparseEmbedder(),
        vector_db=vector_db,
        sc_repo=FakeSourceConnectionRepository(),
        source_registry=FakeSourceRegistry(),
        source_lifecycle=FakeSourceLifecycleService(),
        access_broker=FakeAccessBroker(),
    )


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.organization.id = uuid4()
    ctx.request_id = str(uuid4())
    ctx.logger = MagicMock()
    return ctx


async def _plan_sent_to_the_index(
    plan: SearchPlan, user_filter: list[FilterGroup] | None = None
) -> SearchPlan:
    vector_db = FakeVectorDB()
    vector_db.seed_results(SearchResults(results=[]))
    await _executor(vector_db).execute(
        plan=plan,
        user_filter=user_filter or [],
        collection_ids=["col-1"],
        db=AsyncMock(),
        ctx=_ctx(),
        collection_readable_id="my-collection",
    )
    compiled = [c for c in vector_db._calls if c[0] == "compile_query"]
    assert len(compiled) == 1
    return compiled[0][1]


def _exclusions(group: FilterGroup) -> list[FilterCondition]:
    return [
        c
        for c in group.conditions
        if c.field == ENTITY_TYPE and c.operator == FilterOperator.NOT_IN
    ]


def test_the_upload_connection_is_browse_only_and_its_files_are_not() -> None:
    assert GooclaimUploadConnectionEntity.browse_only is True
    assert GooclaimUploadFileEntity.browse_only is False
    assert BaseEntity.browse_only is False
    types = browse_only_entity_types()
    assert "GooclaimUploadConnectionEntity" in types
    assert "GooclaimUploadFileEntity" not in types


@pytest.mark.asyncio
async def test_a_plain_search_excludes_browse_only_entities() -> None:
    plan = await _plan_sent_to_the_index(
        SearchPlan(
            query=SearchQuery(primary="lumbo sacral belt"),
            limit=10,
            offset=0,
            retrieval_strategy=RetrievalStrategy.HYBRID,
        )
    )
    assert len(plan.filter_groups) == 1
    [exclusion] = _exclusions(plan.filter_groups[0])
    assert isinstance(exclusion.value, list)
    assert "GooclaimUploadConnectionEntity" in exclusion.value


@pytest.mark.asyncio
async def test_the_exclusion_is_anded_into_every_group_the_model_wrote() -> None:
    """The exclusion lands in every group the model wrote.

    The LLM's filter groups are OR'd with each other: an exclusion in only one
    of them would let the connection back in through the others.
    """
    llm_groups = [
        FilterGroup(
            conditions=[
                FilterCondition(
                    field=FilterableField.SYSTEM_METADATA_SOURCE_NAME,
                    operator=FilterOperator.EQUALS,
                    value="gooclaim_upload",
                )
            ]
        ),
        FilterGroup(
            conditions=[
                FilterCondition(
                    field=FilterableField.NAME, operator=FilterOperator.CONTAINS, value="IRDA"
                )
            ]
        ),
    ]
    plan = await _plan_sent_to_the_index(
        SearchPlan(
            query=SearchQuery(primary="q"),
            limit=10,
            offset=0,
            retrieval_strategy=RetrievalStrategy.HYBRID,
            filter_groups=llm_groups,
        )
    )
    assert len(plan.filter_groups) == 2
    for group in plan.filter_groups:
        assert len(_exclusions(group)) == 1


@pytest.mark.asyncio
async def test_a_callers_own_filter_is_kept_alongside_it() -> None:
    caller = [
        FilterGroup(
            conditions=[
                FilterCondition(
                    field=FilterableField.SYSTEM_METADATA_SOURCE_NAME,
                    operator=FilterOperator.EQUALS,
                    value="gooclaim_upload",
                )
            ]
        )
    ]
    plan = await _plan_sent_to_the_index(
        SearchPlan(
            query=SearchQuery(primary="q"),
            limit=10,
            offset=0,
            retrieval_strategy=RetrievalStrategy.HYBRID,
        ),
        caller,
    )
    [group] = plan.filter_groups
    fields = {(c.field, c.operator) for c in group.conditions}
    assert (FilterableField.SYSTEM_METADATA_SOURCE_NAME, FilterOperator.EQUALS) in fields
    assert len(_exclusions(group)) == 1


def test_vespa_receives_a_not_contains_on_the_entity_type() -> None:
    """The condition as the index actually reads it."""
    group = FilterGroup(
        conditions=[
            FilterCondition(
                field=ENTITY_TYPE, operator=FilterOperator.NOT_IN, value=browse_only_entity_types()
            )
        ]
    )
    yql = FilterTranslator(logger=MagicMock()).translate([group])
    assert yql is not None
    assert (
        "!(data_sources_system_metadata_entity_type contains 'GooclaimUploadConnectionEntity')"
        in yql
    )
