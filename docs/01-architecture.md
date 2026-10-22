# 01 — Architecture

## Components (as run by `docker/docker-compose.yml`)

| Container | Image / entry | Role |
|---|---|---|
| `backend` | backend image, code bind-mounted from `../backend` | FastAPI API on 8001, metrics on 9090; runs Alembic on start |
| `temporal-worker` | same image, `python -m airweave.domains.temporal.worker` | Runs syncs: fetch → convert/OCR → chunk → embed → write to Vespa |
| `frontend` | `FRONTEND_IMAGE` (profile `frontend`) | Data Sources UI, built with `VITE_GOOCLAIM_MODE=true` |
| `postgres` | `postgres:16` | Metadata DB `airweave`, plus `svix` and Temporal databases |
| `redis` | `redis:7-alpine` | Pub/sub, caches, Svix queue |
| `temporal`, `temporal-init`, `temporal-ui` | Temporal 1.24 auto-setup | Workflow engine; `temporal-init` registers the `SyncId` search attribute |
| `vespa`, `vespa-init` | `vespaengine/vespa:8` | Index; `vespa-init` deploys `vespa/app` on start |
| `svix` | `svix/svix-server` | Delivers outbound webhooks (to `gooclaim-audit`) |
| `connect`, `text2vec-transformers`, `docling` | profiles | Upstream extras, not part of the Gooclaim setup |

`backend`, `frontend`, `temporal-worker` and `temporal-ui` restart `unless-stopped`.

## Tenancy model

- One Airweave **organization per tenant**, with the tenant's UUID as its id. It is
  created on the first request that names it in `X-Organization-ID`, when
  `EXTERNAL_ORG_ID_PROVISIONING=true` and `AUTH_ENABLED=false`
  (`backend/airweave/api/context_resolver.py`, `_get_or_fetch_organization` /
  `_auto_provision_organization`). Its name comes from `X-Gck-Tenant-Name`; its
  `org_metadata` records `gooclaim_tenant_id`; the system superuser (`FIRST_SUPERUSER`)
  is added as owner.
- There are no per-person user rows. Browser requests run as the system superuser;
  the real caller's email arrives in `X-Gck-User-Email` and is used for display and for
  "created by" fields.
- A **collection** belongs to one organization. `audience` (`members` / `staff`) is
  required and fixed. `is_public` makes it readable — never writable — by every
  organization (`crud/crud_collection.py`).

## Request flows

**Browser (Data Sources UI).** Portal asks `gooclaim-auth` for a bridge session; the
browser then calls the Data Sources API through a front proxy. The proxy checks the
session with `gooclaim-auth` (`GET /v1/auth/airweave-verify`) and forwards
`X-Organization-Id`, `X-Gck-Tenant-Name`, `X-Gck-User-Email`, `X-Gck-Platform-Admin` and
`X-Gck-Return-Url` from that response. The proxy configuration is not in this repository.

**Service (datasources MCP).** `gooclaim-datasources-mcp` calls the backend with a
**master** API key in `X-API-Key` and the tenant in `X-Organization-Id`. An `X-API-Key`
is checked first, before the `AUTH_ENABLED` short-circuit; a key marked `is_master`
skips the "key's org must match the header" check.

Every API request sets the gateway tenant to the request's organization
(`api/deps.py`, `set_gateway_tenant`).

## Sync flow

1. Upload: `POST /uploads/{bucket}` writes the file and a `.gooclaim.json` sidecar to
   `STORAGE_PATH/uploads/{organization_id}/{bucket}/`.
2. Commit: `POST /uploads/{bucket}/commit` creates or reuses the collection
   (`readable_id` = bucket) and a `gooclaim_upload` source connection, then starts a sync.
3. The worker builds the sync context and sets the gateway tenant to the sync's
   organization (`domains/sync_pipeline/builders/sync.py`).
4. `GooclaimUploadSource` gives the pipeline a **temporary copy** of each file (the
   pipeline deletes `local_path` after a batch), so the original stays.
5. Conversion: PDFs and Office files go to OCR. With `LLM_GATEWAY_URL` set, one request
   per part to the gateway's `/v1/ocr` (model `mistral-ocr-latest`, document inline as a
   data URL). Page starts are recorded (`domains/ocr/pages.py`).
6. Chunking, embedding through `OPENAI_BASE_URL`, write to Vespa with
   `data_sources_system_metadata_page_start` / `_page_end`.

Other connectors (including Gooclaim's `s3`) follow the same pipeline from step 3.

## Search flow (classic)

1. `POST /collections/{readable_id}/search/classic`.
2. The search targets the collection **plus every Public collection** in one Vespa
   query (`VespaVectorDB._build_collection_clause`), so ranking stays comparable.
3. Browse-only entities are dropped from ranked results (`domains/search/executor.py`).
4. With `LLM_GATEWAY_URL` and `LLM_GATEWAY_API_KEY` set, the relevance gate
   (`adapters/reranker/relevance_gate.py`) asks the gateway alias `fast` to grade every
   passage 0–3 with a strict per-passage schema and keeps grades 2 and 3. Zero kept is an
   empty result. A gate failure raises: the search fails rather than returning ungated
   results.
5. The answer step uses the search LLM chain (`LLM_FALLBACK_CHAIN`, default Together then
   Anthropic). Only the Anthropic client is gateway-aware.

## Gateway wiring

`backend/airweave/core/gateway_tenant.py` holds the current organization in a
`ContextVar` and provides `tenant_event_hooks()`, an httpx request hook that sets:

| Header | Value |
|---|---|
| `x-litellm-customer-id` | organization id (= tenant id), when one is set |
| `x-litellm-spend-logs-metadata` | `{"feature":"documents"}` unless the caller set one |
| `x-litellm-tags` | `feature:documents` unless the caller set one |

The hook is attached only when the client's base URL is the gateway:

| AI call | Client | Enabled by |
|---|---|---|
| Dense embeddings | `domains/embedders/dense/openai.py` | `OPENAI_BASE_URL` |
| Search LLM (old pipeline) | `search/providers/openai.py` | `OPENAI_BASE_URL` |
| Search LLM (current pipeline) | `adapters/llm/anthropic.py` | `ANTHROPIC_BASE_URL`, model `ANTHROPIC_GATEWAY_MODEL` |
| OCR | `domains/ocr/mistral/ocr_client.py` | `LLM_GATEWAY_URL` + `LLM_GATEWAY_API_KEY` |
| Relevance gate | `adapters/reranker/relevance_gate.py` | `LLM_GATEWAY_URL` + `LLM_GATEWAY_API_KEY` |

Not gateway-aware (they call the provider directly if their key is set, so the key must
stay unset): Together, Groq, Cerebras and Mistral search LLMs, the Mistral embedder, the
Cohere reranker, Azure Document Intelligence OCR. The semantic chunker in
`CHUNKER_EMBEDDER=openai` mode uses `OPENAI_BASE_URL` but without the tenant hook; the
default (`model2vec`) runs locally.

## State

| Store | Gooclaim additions |
|---|---|
| Postgres | `collection.is_public` (0001), `api_key.is_master` (0002), `collection.audience` + check constraint (0003), upload buckets moved under their organization (0004, a file move run once on backend start) |
| Vespa | `data_sources_system_metadata_*` field names (renamed from `airweave_system_metadata_*`), `page_start` / `page_end` |
| Disk (`local_storage`) | `uploads/{organization_id}/{bucket}/` with sidecars; mounted in backend **and** worker |
