# airweave-fork — Gooclaim Data Sources

[![Upstream](https://img.shields.io/badge/upstream-airweave--ai%2Fairweave-0066FF)](https://github.com/airweave-ai/airweave)
[![Python](https://img.shields.io/badge/python-3.13-blue)](backend/pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-6e6e6e)](LICENSE)

> Gooclaim's fork of the open-source [Airweave](https://github.com/airweave-ai/airweave)
> project. It runs as **Data Sources**, the document library of Gooclaim OS: tenants
> upload or connect documents, and the member-question workflow and Orion search them
> with page-level citations. Every AI call it makes goes through Gooclaim's LiteLLM
> gateway and is billed to the tenant.

In anything a user sees, this surface is called **Data Sources**, never "Airweave".

---

## Table of Contents

1. [What This Service Does](#what-this-service-does)
2. [How It Differs From Upstream](#how-it-differs-from-upstream)
3. [Architecture & Position](#architecture--position)
4. [Quick Start](#quick-start)
5. [API Reference](#api-reference)
6. [Configuration](#configuration)
7. [Database / State](#database--state)
8. [Observability](#observability)
9. [Testing](#testing)
10. [Deployment](#deployment)
11. [Versioning](#versioning)
12. [Upstream](#upstream)
13. [Documentation](#documentation)

---

## What This Service Does

- **Holds each tenant's libraries.** A library is an Airweave *collection*. Every
  collection belongs to one organization, and the organization id **is** the Gooclaim
  tenant id: it is created on the tenant's first request, with the tenant's UUID.
- **Says who a library answers.** Every collection has an `audience`: `members` (may be
  used to answer a member) or `staff` (searched by Orion only). It is required when the
  collection is created and cannot be defaulted.
- **Takes uploads.** The *Native Upload* source (`gooclaim_upload`) stores files a tenant
  uploads in a per-tenant bucket on the backend's disk, then syncs them into the index.
- **Reads documents.** Files are converted (OCR through the gateway), chunked, embedded
  (through the gateway) and written to Vespa. Each chunk records the page range it came
  from.
- **Answers searches.** `classic` search ranks the collection, then a relevance gate (a
  small model behind the gateway) keeps only passages graded as answering the question,
  so "not in your documents" is a possible answer.
- **Opens the source.** A cited passage can be fetched in full, and for native uploads
  the original file can be downloaded, always from the caller's own tenant.
- **Shares regulatory knowledge.** A platform admin can mark a collection *Public*; every
  tenant's search then also ranks it.
- **Serves the Data Sources UI** (the forked React frontend, built in Gooclaim mode).

**It does not:**

- decide what a member is told — the engine and the policy gate (L6) do that; this
  service returns passages;
- enforce the `members` / `staff` split on search — it stores the audience; the caller
  (`gooclaim-datasources-mcp`) decides which libraries a caller may search;
- authenticate users itself — Auth0 is off (`AUTH_ENABLED=false`); a front proxy that
  checks the Gooclaim session is the trust boundary (see [Security](docs/11-security.md));
- write audit events directly — sync and connection events reach `gooclaim-audit` as
  webhooks;
- hold provider API keys when run as Gooclaim intends — model calls go to the gateway.

---

## How It Differs From Upstream

The fork is upstream Airweave at commit `a9c8b1af7` (upstream PR #1787, 2026-05-18) plus
94 Gooclaim commits on `release/dev`. Upstream has not been merged in since. The
Gooclaim changes, by area:

| Area | Change | Main files |
|---|---|---|
| Tenancy bridge | `EXTERNAL_ORG_ID_PROVISIONING`: an unknown `X-Organization-ID` UUID auto-creates the organization (named from `X-Gck-Tenant-Name`), owned by the system superuser | `backend/airweave/api/context_resolver.py` |
| Trusted headers | `X-Gck-Platform-Admin`, `X-Gck-User-Email`, `X-Gck-Return-Url`, `X-Gck-Tenant-Name` are read from the front proxy | `backend/airweave/api/deps.py`, `api/context.py`, `endpoints/users.py` |
| Platform-admin gates | Org create/delete, the cross-org admin endpoints and the Public/Private toggle require `X-Gck-Platform-Admin: true`; `/users/me/organizations` is scoped to the current tenant | `endpoints/organizations.py`, `endpoints/admin.py`, `endpoints/collections.py`, `endpoints/users.py` |
| Master API key | `api_key.is_master` lets one key act for any organization named in `X-Organization-ID`; an `X-API-Key` is checked before the `AUTH_ENABLED` short-circuit | `context_resolver.py`, migration `0002` |
| LLM gateway | Embeddings, search LLM (Anthropic), OCR (Mistral) and the relevance gate go through LiteLLM; each request carries `x-litellm-customer-id` = organization id and the label `feature:documents` | `backend/airweave/core/gateway_tenant.py` and its callers |
| Relevance gate | Classic search keeps only passages graded 2 or 3 (of 0–3) by the gateway's `fast` alias; browse-only entities never reach ranked results | `adapters/reranker/relevance_gate.py`, `domains/search/executor.py` |
| Library audience | `collection.audience` (`members` / `staff`), required on create, fixed afterwards | `models/collection.py`, `schemas/collection.py`, migration `0003` |
| Public collections | `collection.is_public`; reads OR in Public collections; search ranks own + Public collections in one Vespa query | `crud/crud_collection.py`, `domains/search/adapters/vector_db/vespa_client.py`, migration `0001` |
| Native Upload | New source `gooclaim_upload` and `/uploads/*` routes; buckets at `STORAGE_PATH/uploads/{organization_id}/{bucket}`; the original is never handed to the pipeline (it would be deleted) | `platform/sources/gooclaim_upload.py`, `api/v1/endpoints/uploads.py`, migration `0004` |
| AWS S3 source | New source `s3` (also S3-compatible stores), with Bedrock-style `.metadata.json` sidecars | `platform/sources/s3.py` |
| Pages and citations | OCR records where each page begins; chunks carry `page_start` / `page_end`; `GET /entities/{id}/content` and `/original` are scoped to collections the caller may read | `domains/ocr/pages.py`, `vespa/app/schemas/base_entity.sd`, `endpoints/entities.py` |
| Field rename | Vespa and search fields `airweave_system_metadata_*` → `data_sources_system_metadata_*` | `vespa/app/schemas/*.sd`, search and destination code |
| Limits | `API_REQUEST_BODY_SIZE_LIMIT` 10 MiB → 50 MiB, matching the UI's per-file cap | `core/config/settings.py` |
| Compose | `extra_hosts` on the worker (so it can reach the gateway), `local_storage` mounted in the worker, `restart: unless-stopped` on long-running services | `docker/docker-compose.yml` |
| Frontend | Gooclaim mode (`VITE_GOOCLAIM_MODE=true`): Gooclaim OS branding, "Back to portal" instead of sign-out, no billing / members / API-key self-service, Native Upload view with library choice, Request Connector modal, admin dashboard for platform admins only | `frontend/.env.production`, `frontend/src/config/env.ts` and the views it gates |
| Removed gates | Upstream's `COLLECTION_BROWSE` feature flag and a hard-coded customer-org gate on file retrieval | `endpoints/search.py`, `endpoints/file_retrieval.py` |

The full commit list: `git log --oneline a9c8b1af7..release/dev`.

---

## Architecture & Position

```
 Portal / Console (browser)                    gooclaim-engine      gooclaim-orion-api
        │ Data Sources UI                           │ MCP                 │ MCP
        ▼                                           ▼                     ▼
 front proxy ── checks the Gooclaim session   gooclaim-datasources-mcp (gooclaim-mcp-server)
   (auth_request → gooclaim-auth)                   │ X-API-Key (master) + X-Organization-Id
        │ sets X-Organization-ID, X-Gck-*           │
        ▼                                           ▼
 ┌──────────────────────── airweave-fork ─────────────────────────────┐
 │ frontend (React, :8080)     backend (FastAPI, :8001, metrics :9090) │
 │                                  │ start sync                        │
 │                                  ▼                                   │
 │                     Temporal ── temporal-worker (sync pipeline)      │
 │                                  │                                   │
 │   Postgres (metadata) · Redis (pub/sub, cache) · Vespa (index)      │
 │   Svix (outbound webhooks) · local_storage volume (uploads)         │
 └──────────────┬──────────────────────────────┬──────────────────────┘
                │ embeddings, OCR, search LLM,  │ sync_job.* / connection.*
                ▼ relevance gate                ▼ webhooks
          LiteLLM gateway                  gooclaim-audit  POST /v1/audit/airweave-webhook
```

The engine (member questions) and Orion (staff) never call this service directly; both
go through `gooclaim-datasources-mcp`, which holds the master key and decides which
libraries each caller may search.

### Hard rules

1. **The organization id is the tenant id.** Never map, rename or re-key organizations;
   `gooclaim-audit` and the gateway bill by this id.
2. **The front proxy is the trust boundary.** With `AUTH_ENABLED=false` and
   `EXTERNAL_ORG_ID_PROVISIONING=true`, a request without an API key runs as the system
   superuser for whatever organization the header names. The backend port must only be
   reachable through the proxy, and the proxy must overwrite every `X-Gck-*` and
   `X-Organization-ID` header.
3. **Every AI call goes through the gateway and names the tenant.** Attach
   `tenant_event_hooks()` to any new AI client whose base URL is the gateway; never add
   a provider key.
4. **A library's audience is chosen, never defaulted.** Do not add a default to
   `CollectionCreate.audience`.
5. **An upload bucket belongs to one organization.** Resolve buckets only with
   `bucket_dir(organization_id, bucket)`; never read a path an entity or config names.
6. **The original upload is never handed to the pipeline.** The pipeline deletes each
   file entity's `local_path` after a batch; give it a temporary copy.
7. **Classic search may return nothing.** If the relevance gate fails, the search fails;
   never fall back to ungated results.
8. **Never log a query or a passage.** A member's question can carry PHI.

---

## Quick Start

### Prerequisites

- Docker with Compose
- Python 3.13 and Poetry (for running backend tests outside Docker)
- Node 20 (for frontend work outside Docker)
- A reachable LiteLLM gateway and a virtual key for it, if you want AI calls to work

### Install

```bash
git clone https://github.com/gooclaim-claimos/airweave-fork.git
cd airweave-fork
git checkout release/dev

# Backend dependencies (for tests and local tooling)
cd backend && poetry install && cd ..
```

Create `.env` in the repo root (upstream's `./start.sh` generates one from
`.env.example`). For Gooclaim behaviour add at least:

```bash
EXTERNAL_ORG_ID_PROVISIONING=true
OPENAI_BASE_URL=<gateway OpenAI-compatible base URL>     # embeddings
OPENAI_API_KEY=<gateway virtual key>
ANTHROPIC_BASE_URL=<gateway base URL>                    # search LLM
ANTHROPIC_API_KEY=<gateway virtual key>
ANTHROPIC_GATEWAY_MODEL=smart
LLM_GATEWAY_URL=<gateway base URL>                       # OCR + relevance gate
LLM_GATEWAY_API_KEY=<gateway virtual key>
```

### Run

```bash
cd docker
docker compose --env-file ../.env up -d
docker compose --env-file ../.env --profile frontend up -d frontend   # UI
```

`--env-file ../.env` is required: compose reads `${BACKEND_IMAGE}`, `${SVIX_JWT_SECRET}`
and the other `${...}` values from it. Without it the backend and worker start on the
**upstream** image with an empty Svix secret (see [Deployment](#deployment)).

Backend: `http://localhost:8001` (API docs at `/docs`) · UI: `http://localhost:8080` ·
Temporal UI: `http://localhost:8088`.

---

## API Reference

Routes are mounted at the root (no `/api/v1` prefix). Below is only the surface Gooclaim
services call or that Gooclaim added; upstream's full API is in the
[upstream docs](https://docs.airweave.ai). Details: [docs/03-apis.md](docs/03-apis.md).

| Method & path | Caller | Purpose |
|---|---|---|
| `GET /collections` | datasources MCP, UI | Libraries of the tenant (own + Public), with `audience` |
| `POST /collections/{readable_id}/search/classic` | datasources MCP | Search with the relevance gate; body `{"query", "limit"}` |
| `POST /collections/{readable_id}/search/browse` | datasources MCP | Browse a collection |
| `GET /entities/{entity_id}/content` | datasources MCP | Full fields of one chunk, only from a collection the caller may read |
| `GET /entities/{entity_id}/original` | datasources MCP | Original file of a native upload (404 for other sources) |
| `GET /sources`, `GET /source-connections` | datasources MCP | Connectors and the tenant's connections |
| `GET /files/{entity_id}`, `GET /files/{entity_id}/content` | datasources MCP | File metadata and content |
| `GET /entity-counts/syncs/{sync_id}/total-count` | datasources MCP | Entities indexed by a sync |
| `POST /uploads/{connection_id}` | UI | Upload one file (≤ 50 MiB, supported extensions only) |
| `GET /uploads/{connection_id}` | UI | List a bucket's uploads |
| `POST /uploads/{connection_id}/commit` | UI | Create or reuse the collection and `gooclaim_upload` connection, then sync |
| `PATCH /collections/{readable_id}/visibility` | UI (platform admin) | Public / Private |
| `GET /users/me` | UI | Adds `is_platform_admin`, `return_url`, and the real caller's email |
| `GET /health`, `/health/live`, `/health/ready` | compose, proxy | Health |

Every tenant-scoped call carries `X-Organization-ID` (the tenant UUID). Services
authenticate with `X-API-Key`; the browser path is authenticated by the front proxy.

---

## Configuration

### Repository Structure

```
backend/                 FastAPI app, sync pipeline, Temporal worker (python -m airweave.domains.temporal.worker)
  airweave/core/gateway_tenant.py          tenant header + label on every gateway call
  airweave/api/context_resolver.py         auth order, org auto-provisioning, master key
  airweave/api/v1/endpoints/uploads.py     Native Upload routes
  airweave/platform/sources/gooclaim_upload.py, s3.py
  airweave/adapters/reranker/relevance_gate.py
  alembic/versions/                        0000 baseline (upstream) + 0001–0004 (Gooclaim)
  tests/                                   tests/unit, tests/integration, tests/e2e
frontend/                React/Vite UI; .env.production sets VITE_GOOCLAIM_MODE=true
docker/docker-compose.yml                  the stack Gooclaim runs
vespa/app/                                 Vespa application package (deployed by vespa-init)
helm/datasources-*/                        Kubernetes charts — not used by the running environment
fern/, mcp/, connect/, monke/              upstream (docs site, MCP server, Connect widget, connector E2E)
```

### Wire / Ports

| Port | Service | Notes |
|---|---|---|
| 8001 | backend | HTTP API; must sit behind the front proxy |
| 9090 | backend | Prometheus metrics (`METRICS_PORT`) |
| 8080 | frontend | `frontend` compose profile |
| 7233 / 8233 | Temporal | |
| 8088 | Temporal UI | |
| 8081 / 19071 | Vespa | query / config server |
| 8071 | Svix | outbound webhooks |
| 5432 / 6379 | Postgres / Redis | |

The worker's control server (`/health`, `/drain`) listens on `WORKER_METRICS_PORT`
(8888) inside the container and is not published by compose.

### Environment Variables

The settings class is `backend/airweave/core/config/settings.py`; a few Gooclaim
variables are read with `os.getenv` at the client that uses them. Only Gooclaim-relevant
ones are listed; the full list is in [docs/05-configuration.md](docs/05-configuration.md).

| Variable | Default | Required | Purpose |
|---|---|---|---|
| `AUTH_ENABLED` | `False` | — | Compose forces `false` on the backend |
| `EXTERNAL_ORG_ID_PROVISIONING` | `False` | yes (Gooclaim) | Auto-create orgs from `X-Organization-ID`; turns on the platform-admin gates |
| `FIRST_SUPERUSER` / `FIRST_SUPERUSER_PASSWORD` | — | yes | System user; owner of every auto-provisioned org |
| `ENCRYPTION_KEY`, `STATE_SECRET`, `SVIX_JWT_SECRET` | — | yes | Upstream secrets |
| `POSTGRES_HOST` / `_USER` / `_PASSWORD` | — | yes | Metadata DB |
| `OPENAI_BASE_URL` (env) | unset | yes (Gooclaim) | Gateway URL for embeddings; enables the tenant header |
| `OPENAI_API_KEY` | `None` | yes | Gateway virtual key when `OPENAI_BASE_URL` is set |
| `ANTHROPIC_BASE_URL` (env) | unset | yes (Gooclaim) | Gateway URL for the search LLM |
| `ANTHROPIC_API_KEY` | `None` | yes | Gateway virtual key; without it classic/agentic search return 503 |
| `ANTHROPIC_GATEWAY_MODEL` (env) | model spec name | yes (Gooclaim) | Alias the gateway serves (`smart`) |
| `LLM_GATEWAY_URL` / `LLM_GATEWAY_API_KEY` (env) | unset | yes (Gooclaim) | OCR via the gateway's `/v1/ocr`; turns on the relevance gate |
| `TOGETHER_API_KEY`, `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `MISTRAL_API_KEY`, `COHERE_API_KEY` | `None` | **leave unset** | Would call that provider directly, bypassing the gateway |
| `AZURE_DI_ENDPOINT` / `AZURE_DI_KEY` | `None` | **leave unset** | Direct Azure OCR, tried before Mistral |
| `STORAGE_PATH` | `./local_storage` | — | Root of upload buckets (`/app/local_storage` in compose) |
| `API_REQUEST_BODY_SIZE_LIMIT` | 50 MiB | — | Must be ≥ the UI's 50 MiB file cap |
| `ANALYTICS_ENABLED` | `True` | set `false` | When `ENVIRONMENT` is not `local`, the backend sends product analytics to upstream's PostHog project |

Compose-only: `BACKEND_IMAGE`, `FRONTEND_IMAGE`, `API_URL`, `ENVIRONMENT`.

---

## Database / State

| Store | What | Notes |
|---|---|---|
| Postgres (`airweave` DB) | organizations, collections (`audience`, `is_public`), source connections, syncs, API keys (`is_master`) | Alembic runs on backend start; revisions `0000` (upstream baseline) → `0004` |
| Postgres (`svix` DB) | Svix webhook state | Created by `docker/init-scripts` |
| Vespa | chunks with embeddings, `data_sources_system_metadata_*` fields, `page_start` / `page_end` | Application package `vespa/app`, deployed by `vespa-init` |
| `local_storage` volume | Native Upload buckets `uploads/{organization_id}/{bucket}/`, each file with a `.gooclaim.json` sidecar | Mounted in **both** backend and worker |
| Redis | pub/sub, caches, Svix queue | |
| Temporal | sync workflows (task queue `airweave-sync-queue`) | |

Gooclaim migrations: `0001` collection `is_public` · `0002` api_key `is_master` (set only
in the database, never by an API) · `0003` collection `audience` with a check
constraint · `0004` moves upload buckets under their organization (data move, runs
once on the backend).

---

## Observability

- **Logs:** structlog via `airweave.core.logging`; API requests are bound to
  `request_id`, `organization_id`, `auth_method`. The relevance gate and upload code never
  log a query, a passage or file content.
- **Metrics:** Prometheus on `METRICS_PORT` (9090) — HTTP, DB pool, agentic search.
- **Health:** `GET /health/ready` (compose healthcheck), `/health/live`, `/health`.
- **AI spend:** every gateway request carries `x-litellm-customer-id` (organization id),
  `x-litellm-spend-logs-metadata: {"feature":"documents"}` and
  `x-litellm-tags: feature:documents`, so LiteLLM spend logs show the tenant and feature.
- **Audit:** sync and connection events leave through Svix webhooks to
  `gooclaim-audit`, which writes them to the ledger as `DATA_SOURCES_*` events.

---

## Testing

Backend tests live in **two** trees, and `pytest.ini` only collects `tests/`:

```bash
cd backend
poetry run pytest -q tests/unit airweave -n 4     # both trees (xdist)
poetry run ruff check . && poetry run ruff format --check .
```

`backend/conftest.py` sets the environment `Settings` needs, so no `.env` is required.
A run of `tests/unit` alone misses the domain tests under `airweave/**/tests/`.
Before calling a failure pre-existing, run the same command on the base commit.

Frontend: `cd frontend && npm run lint && npm run build`.

There is no server CI for `release/dev` (`.github/workflows/gooclaim-ci.yml` only
triggers on `develop`). Run the checks locally before every push. More:
[docs/08-testing.md](docs/08-testing.md).

---

## Deployment

On dev, the stack runs on an AWS EC2 instance with `docker compose` from
`docker/docker-compose.yml`, next to the LiteLLM gateway.

- The backend and worker **bind-mount** `../backend:/app`, so a backend change is
  deployed by copying the committed files (`git archive`) into place and recreating
  `backend` and `temporal-worker`. Alembic migrations run when the backend starts.
- The frontend is an image (`FRONTEND_IMAGE` in `.env`) built from `frontend/`; keep the
  previous image for rollback.
- Always pass the env file:

  ```bash
  cd docker
  docker compose --env-file ../.env -f docker-compose.yml config | grep image   # check first
  docker compose --env-file ../.env -f docker-compose.yml \
    up -d --no-deps --force-recreate backend temporal-worker
  ```

  Without `--env-file ../.env`, compose falls back to
  `ghcr.io/airweave-ai/airweave-backend:latest` and sets `SVIX_JWT_SECRET` to empty,
  which overrides the `env_file` value; the backend then fails settings validation and
  crash-loops.
- The live compose file and `.env` on the instance may differ from the repo (for example
  the Temporal namespace). Do not copy the repo's compose over them.

Full runbook: [docs/06-deployment.md](docs/06-deployment.md).

---

## Versioning

The fork has no version of its own (`backend/pyproject.toml` keeps upstream's `0.1.0`).
A deployment is identified by its `release/dev` commit. Branches:
`feature|fix|chore|docs/<x>` → `release/dev` → `release/uat` → `main` → `release/prd`;
today only `release/dev` carries the current code. Push and open PRs against
`gooclaim-claimos/airweave-fork` only, never upstream.

---

## Upstream

Everything not listed above behaves as upstream Airweave: connectors, sync pipeline,
search tiers, SDKs, CLI, Connect widget and the MCP server in `mcp/`.

- Upstream repository: <https://github.com/airweave-ai/airweave>
- Upstream documentation: <https://docs.airweave.ai> (source in `fern/`)
- Contributing upstream: [CONTRIBUTING.md](CONTRIBUTING.md) — Gooclaim changes are never
  contributed back.

Rebasing on upstream: [docs/gooclaim-fork-rebase.md](docs/gooclaim-fork-rebase.md).

---

## Documentation

See [docs/README.md](docs/README.md) for the Gooclaim-specific documentation set.

License: [MIT](LICENSE) (upstream's licence, unchanged).
