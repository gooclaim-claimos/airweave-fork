"""API endpoints for entity definitions, relations, and direct doc lookup."""

import httpx
from fastapi import Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from airweave.api import deps
from airweave.api.context import ApiContext
from airweave.api.deps import Inject
from airweave.api.router import TrailingSlashRouter
from airweave.core.config import settings
from airweave.domains.entities.protocols import EntityDefinitionRegistryProtocol
from airweave.domains.entities.types import EntityDefinitionMetadata
from airweave.models.collection import Collection

router = TrailingSlashRouter()

# Vespa namespace is fixed at "airweave" (the deployed Vespa app uses this
# as the addressing namespace in document IDs — distinct from any product
# naming choice in the rest of the codebase, see Vespa docs on namespaces).
# Doc IDs look like: id:airweave:{schema}::{entity_id}
_VESPA_NAMESPACE = "airweave"

# Schemas to probe in order when an entity_id's source schema is unknown.
# Matches the .sd files under vespa/app/schemas/. The first hit wins.
# ``base_entity`` is probed LAST as the catch-all: generic sources that
# don't map to a specialised schema (e.g. ``gooclaim_upload`` native
# uploads) index there, so omitting it 404'd every native-upload lookup.
_VESPA_SCHEMAS = (
    "file_entity",
    "email_entity",
    "code_file_entity",
    "web_entity",
    "base_entity",
)


@router.get("/definitions/by-source/", response_model=list[EntityDefinitionMetadata])
async def get_entity_definitions_by_source_short_name(
    source_short_name: str,
    registry: EntityDefinitionRegistryProtocol = Inject(EntityDefinitionRegistryProtocol),
) -> list[EntityDefinitionMetadata]:
    """Get all entity definitions for a given source."""
    entries = registry.list_for_source(source_short_name)
    return [
        EntityDefinitionMetadata(
            short_name=entry.short_name,
            name=entry.name,
            description=entry.description,
            class_name=entry.class_name,
            module_name=entry.module_name,
            entity_type=entry.entity_type,
            entity_schema=entry.entity_schema,
        )
        for entry in entries
    ]


#: An entity_id is unique within a collection, not across organisations — ask
#: Vespa for enough matches that the caller's own copy is among them.
_ENTITY_MATCHES = 50


async def _readable_collection_ids(db: AsyncSession, ctx: ApiContext) -> set[str]:
    """The collections this caller may read.

    Its organisation's own, and public ones — the same rule classic search
    applies (`get_by_readable_id`).
    """
    rows = await db.execute(
        select(Collection.id).where(
            or_(Collection.organization_id == ctx.organization.id, Collection.is_public.is_(True))
        )
    )
    return {str(cid) for cid in rows.scalars()}


@router.get("/{entity_id}/content")
async def get_entity_content_by_id(
    entity_id: str,
    ctx: ApiContext = Depends(deps.get_context),
    db: AsyncSession = Depends(deps.get_db),
) -> dict:
    """Fetch the full content of a single document by entity_id.

    Uses Vespa's YQL search with an exact-match filter on the
    ``entity_id`` field. Works for any entity_id format
    (UUID-based ``gooclaim_upload`` chunks, ``ctti:study:NCT...``, etc.)
    because the filter is a single equality predicate against an
    indexed attribute — not a BM25 text search.

    The Vespa Document API direct-docid lookup would be faster but
    requires knowing the full doc-id which embeds the entity class
    name (e.g. ``GooclaimUploadFileEntity_<uuid>__chunk_0``). Callers
    typically only have the post-``::`` ``entity_id`` portion that
    search results return.

    Args:
        entity_id: The entity ID as returned by ``search_knowledge``.
        ctx: The API context — tenant + org scope.
        db: The session the caller's readable collections are read with.

    Returns:
        ``{entity_id, schema, fields}`` where ``fields`` is the full
        ``document.fields`` payload from Vespa.

    Raises:
        HTTPException: 404 if no schema returned a matching document IN A
            COLLECTION THE CALLER MAY READ. 🔴 Gooclaim: this looked the id up
            across every organisation's index, so a caller holding another
            tenant's chunk id read that tenant's text. Another organisation's
            entity now reads exactly like one that does not exist.
    """
    base = f"{settings.VESPA_URL}:{settings.VESPA_PORT}"
    readable = await _readable_collection_ids(db, ctx)

    async with httpx.AsyncClient(timeout=10.0) as client:
        for schema in _VESPA_SCHEMAS:
            # Vespa YQL: exact attribute match on the entity_id field.
            # Use parameter binding via the JSON query API to avoid YQL
            # injection from user-supplied entity_ids.
            body = {
                "yql": f"select * from {schema} where entity_id contains @eid",
                "eid": entity_id,
                "hits": _ENTITY_MATCHES,
            }
            try:
                resp = await client.post(f"{base}/search/", json=body)
            except httpx.HTTPError as exc:
                ctx.logger.warning(f"[entities] Vespa search {schema}/{entity_id} errored: {exc}")
                continue
            if resp.status_code >= 400:
                ctx.logger.warning(
                    f"[entities] Vespa search {schema}/{entity_id} → "
                    f"HTTP {resp.status_code}: {resp.text[:200]}"
                )
                continue
            data = resp.json()
            children = data.get("root", {}).get("children") or []
            for hit in children:
                fields = hit.get("fields", {})
                # The exact entity_id (not a substring), in a collection the
                # caller may read.
                if fields.get("entity_id") != entity_id:
                    continue
                if str(fields.get("data_sources_system_metadata_collection_id")) not in readable:
                    continue
                return {
                    "entity_id": entity_id,
                    "schema": schema,
                    "fields": fields,
                }

    raise HTTPException(
        status_code=404,
        detail=f"Entity not found: {entity_id}",
    )
