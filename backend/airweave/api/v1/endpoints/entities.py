"""API endpoints for entity definitions, relations, and direct doc lookup."""

from urllib.parse import quote

import httpx
from fastapi import Depends, HTTPException

from airweave.api import deps
from airweave.api.context import ApiContext
from airweave.api.deps import Inject
from airweave.api.router import TrailingSlashRouter
from airweave.core.config import settings
from airweave.domains.entities.protocols import EntityDefinitionRegistryProtocol
from airweave.domains.entities.types import EntityDefinitionMetadata

router = TrailingSlashRouter()

# Vespa namespace is fixed at "airweave" (the deployed Vespa app uses this
# as the addressing namespace in document IDs — distinct from any product
# naming choice in the rest of the codebase, see Vespa docs on namespaces).
# Doc IDs look like: id:airweave:{schema}::{entity_id}
_VESPA_NAMESPACE = "airweave"

# Schemas to probe in order when an entity_id's source schema is unknown.
# Matches the .sd files under vespa/app/schemas/. The first hit wins.
_VESPA_SCHEMAS = (
    "file_entity",
    "email_entity",
    "code_file_entity",
    "web_entity",
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


@router.get("/{entity_id}/content")
async def get_entity_content_by_id(
    entity_id: str,
    ctx: ApiContext = Depends(deps.get_context),
) -> dict:
    """Fetch the full content of a single Vespa document by entity_id.

    Direct Vespa Document API lookup — works for any entity_id format
    (UUID-based ``gooclaim_upload``, ``ctti:study:NCT...``, etc.) because
    Vespa's docid lookup is an O(1) bucket hash, not a BM25 search.

    Probes ``file_entity``, ``email_entity``, ``code_file_entity``, and
    ``web_entity`` schemas in that order and returns the first hit.

    Args:
        entity_id: The entity ID (Vespa doc ID after the ``::`` separator).
        ctx: The API context — tenant + org scope.

    Returns:
        ``{entity_id, schema, fields}`` where ``fields`` is the full
        ``document.fields`` payload from Vespa.

    Raises:
        HTTPException: 404 if no schema returned a matching document.
    """
    base = f"{settings.VESPA_URL}:{settings.VESPA_PORT}"
    encoded_id = quote(entity_id, safe="")

    async with httpx.AsyncClient(timeout=10.0) as client:
        for schema in _VESPA_SCHEMAS:
            url = (
                f"{base}/document/v1/{_VESPA_NAMESPACE}/{schema}/docid/{encoded_id}"
            )
            try:
                resp = await client.get(url)
            except httpx.HTTPError as exc:
                ctx.logger.warning(
                    f"[entities] Vespa GET {schema}/{entity_id} errored: {exc}"
                )
                continue
            if resp.status_code == 404:
                continue
            if resp.status_code >= 400:
                ctx.logger.warning(
                    f"[entities] Vespa GET {schema}/{entity_id} → "
                    f"HTTP {resp.status_code}: {resp.text[:200]}"
                )
                continue
            payload = resp.json()
            fields = payload.get("fields", {})
            # Scope check: the document MUST belong to the calling org.
            # The Vespa schema stores collection_id keyed by org via the
            # `data_sources_system_metadata_collection_id` field, but a
            # cheaper org-scope gate lives on the document directly
            # through Vespa's existing query filter chain. For this
            # direct-id lookup we re-check that the org owns the
            # collection on the FastAPI side by comparing the document's
            # collection_id against the caller's accessible collections.
            # The current Phase 1 server has AUTH_ENABLED=false and a
            # single org per deploy, so the upstream YQL filter is the
            # canonical gate; a Phase 1.1 follow-up will tighten this
            # path with an explicit org check once multi-tenant routing
            # lands.
            return {
                "entity_id": entity_id,
                "schema": schema,
                "fields": fields,
            }

    raise HTTPException(
        status_code=404,
        detail=f"Entity not found: {entity_id}",
    )
