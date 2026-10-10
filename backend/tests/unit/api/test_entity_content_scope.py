"""GET /entities/{entity_id}/content reads only the caller's collections.

Gooclaim: the lookup searched every organisation's index by entity_id, so a
caller holding another tenant's chunk id read that tenant's text. Policy L6
and Orion's citations read chunks by id — they must read their own tenant's.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from airweave.api.v1.endpoints import entities

OURS = str(uuid4())
THEIRS = str(uuid4())


def _ctx():
    ctx = MagicMock()
    ctx.organization = SimpleNamespace(id=uuid4())
    ctx.logger = MagicMock()
    return ctx


def _db(readable: list[str]):
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value = iter(readable)
    db.execute.return_value = result
    return db


def _vespa(hits_by_schema: dict[str, list[dict]]):
    calls: list[dict] = []

    class _Resp:
        status_code = 200

        def __init__(self, hits):
            self._hits = hits

        def json(self):
            return {"root": {"children": [{"fields": f} for f in self._hits]}}

    class _Client:
        def __init__(self, **_kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return None

        async def post(self, url, json):
            calls.append(json)
            schema = json["yql"].split(" from ")[1].split(" ")[0]
            return _Resp(hits_by_schema.get(schema, []))

    return _Client, calls


def _chunk(collection: str, text: str) -> dict:
    return {
        "entity_id": "doc__chunk_0",
        "data_sources_system_metadata_collection_id": collection,
        "textual_representation": text,
    }


@pytest.mark.asyncio
async def test_another_organisations_chunk_reads_as_not_found():
    client, _ = _vespa({"base_entity": [_chunk(THEIRS, "their policy wording")]})
    with patch.object(entities.httpx, "AsyncClient", client):
        with pytest.raises(HTTPException) as exc:
            await entities.get_entity_content_by_id("doc__chunk_0", ctx=_ctx(), db=_db([OURS]))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_the_callers_own_copy_is_found_even_behind_another_organisations():
    client, calls = _vespa(
        {
            "base_entity": [
                _chunk(THEIRS, "their policy wording"),
                _chunk(OURS, "our policy wording"),
            ]
        }
    )
    with patch.object(entities.httpx, "AsyncClient", client):
        got = await entities.get_entity_content_by_id("doc__chunk_0", ctx=_ctx(), db=_db([OURS]))
    assert got["fields"]["textual_representation"] == "our policy wording"
    assert all(call["hits"] == entities._ENTITY_MATCHES for call in calls)


@pytest.mark.asyncio
async def test_an_entity_id_that_only_contains_the_asked_one_is_not_it():
    near = {**_chunk(OURS, "x"), "entity_id": "doc__chunk_0_extra"}
    client, _ = _vespa({"base_entity": [near]})
    with patch.object(entities.httpx, "AsyncClient", client):
        with pytest.raises(HTTPException):
            await entities.get_entity_content_by_id("doc__chunk_0", ctx=_ctx(), db=_db([OURS]))


@pytest.mark.asyncio
async def test_readable_means_the_callers_organisation_or_public_like_search():
    ctx = _ctx()
    db = _db([])
    await entities._readable_collection_ids(db, ctx)
    query = db.execute.await_args.args[0]
    where = str(query.whereclause.compile(compile_kwargs={"literal_binds": True}))
    assert "collection.organization_id = " in where and str(ctx.organization.id).replace(
        "-", ""
    ) in where.replace("-", "")
    assert "collection.is_public IS true" in where and " OR " in where
