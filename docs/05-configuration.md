# 05 — Configuration

Settings come from `backend/airweave/core/config/settings.py` (`Settings`, pydantic
settings, read from the environment). A few Gooclaim variables are not on `Settings` and
are read with `os.getenv` by the client that uses them; they are marked *(env)*.

In compose, the backend and worker read `../.env` through `env_file`, and the
`environment:` block then **overrides** some values (see the last section).

## Gooclaim tenancy and auth

| Variable | Default | Required | Notes |
|---|---|---|---|
| `AUTH_ENABLED` | `False` | — | Compose sets `AUTH_ENABLED=false` on the backend. Turning it on needs a full Auth0 setup Gooclaim does not have |
| `EXTERNAL_ORG_ID_PROVISIONING` | `False` | **yes** for Gooclaim | Auto-creates organizations from `X-Organization-ID`, skips the membership check for system-auth requests, and turns on the platform-admin gates (org create/delete, `/admin/*`, collection visibility, `/users/me/organizations` scoping) |
| `FIRST_SUPERUSER` | — | yes | Email of the system user; owner of every auto-provisioned organization |
| `FIRST_SUPERUSER_PASSWORD` | — | yes | |
| `FIRST_SUPERUSER_NAME` | `Admin` | — | |

## LLM gateway (LiteLLM)

| Variable | Default | Required | Notes |
|---|---|---|---|
| `OPENAI_BASE_URL` *(env)* | unset → OpenAI | **yes** | Gateway's OpenAI-compatible base URL. Used by the dense embedder and the old search pipeline; when set, the tenant hook is attached. An empty value is treated as unset |
| `OPENAI_API_KEY` | `None` | **yes** | The gateway virtual key when `OPENAI_BASE_URL` points at the gateway |
| `DENSE_EMBEDDER` / `EMBEDDING_DIMENSIONS` | `None` | yes | Upstream embedder choice; the model it names must be served by the gateway. Vespa is deployed with `EMBEDDING_DIMENSIONS` (default 1536 in `vespa/init-vespa.sh`) |
| `ANTHROPIC_BASE_URL` *(env)* | unset → Anthropic | **yes** | Gateway base URL for the search LLM |
| `ANTHROPIC_API_KEY` | `None` | **yes** | Gateway virtual key. If no provider in the chain has a key, classic and agentic search return 503 |
| `ANTHROPIC_GATEWAY_MODEL` *(env)* | the model spec's name | **yes** | The alias the gateway serves (`smart`); the gateway refuses vendor names the key is not granted |
| `LLM_FALLBACK_CHAIN` | `None` → `together:…, anthropic:…` | — | Comma-separated `provider:model`. With no Together key, only Anthropic is used |
| `LLM_GATEWAY_URL` *(env)* | unset | **yes** | Enables OCR through the gateway's `/v1/ocr` (no `MISTRAL_API_KEY` needed) and the classic-search relevance gate |
| `LLM_GATEWAY_API_KEY` *(env)* | unset | with `LLM_GATEWAY_URL` | OCR fails with a sync error if the URL is set without the key; the relevance gate needs both |
| `CHUNKER_EMBEDDER` *(env)* | `model2vec` | — | `openai` uses `OPENAI_BASE_URL` for chunk boundaries, without the tenant header |
| `CHUNKER_OPENAI_MODEL` *(env)* | `text-embedding-3-small` | — | Only with `CHUNKER_EMBEDDER=openai` |

### Keys that must stay unset

Each of these makes the backend call a provider directly, bypassing the gateway and
its per-tenant billing:

`TOGETHER_API_KEY`, `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `MISTRAL_API_KEY` (used by the
Mistral LLM and embedder, and by OCR when `LLM_GATEWAY_URL` is unset), `COHERE_API_KEY`
(reranker), `AZURE_DI_ENDPOINT` + `AZURE_DI_KEY` (Azure OCR, tried before Mistral),
`FIRECRAWL_API_KEY`.

## Storage

| Variable | Default | Notes |
|---|---|---|
| `STORAGE_PATH` | `./local_storage` | Native Upload buckets live at `STORAGE_PATH/uploads/{organization_id}/{bucket}`, whatever `STORAGE_BACKEND` says. In compose this is `/app/local_storage`, mounted from `../local_storage` in backend **and** worker |
| `STORAGE_BACKEND` | auto | `filesystem` / `aws` / `azure` / `gcp` for upstream's file storage. If unset: `local`/`test` → filesystem, `dev`/`prd` → **azure** — set it explicitly when `ENVIRONMENT` is not `local` |
| `STORAGE_AWS_BUCKET`, `STORAGE_AWS_REGION`, `STORAGE_AWS_PREFIX`, `STORAGE_AWS_ENDPOINT_URL` | `None` / `""` | Only with `STORAGE_BACKEND=aws` |

The AWS S3 **source connector** (`s3`) takes its bucket and credentials from the source
connection, not from these settings.

## Limits

| Variable | Default | Notes |
|---|---|---|
| `API_REQUEST_BODY_SIZE_LIMIT` | 50 MiB (Gooclaim; upstream 10 MiB) | Must be ≥ the UI's per-file cap (50 MiB) |
| `API_REQUEST_TIMEOUT_SECONDS` | 60 | |

## Upstream settings Gooclaim relies on

| Variable | Default | Required |
|---|---|---|
| `ENCRYPTION_KEY`, `STATE_SECRET`, `SVIX_JWT_SECRET` | — | yes |
| `POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | — | yes |
| `POSTGRES_DB` / `POSTGRES_PORT` | `airweave` / 5432 | — |
| `REDIS_HOST` / `REDIS_PORT` | `localhost` / 6379 | — |
| `VESPA_URL` / `VESPA_PORT` | `http://localhost` / 8081 | — |
| `TEMPORAL_HOST` / `TEMPORAL_PORT` / `TEMPORAL_NAMESPACE` / `TEMPORAL_TASK_QUEUE` | `localhost` / 7233 / `default` / `airweave-sync-queue` | — |
| `SVIX_URL` | `http://localhost:8071` | — |
| `RUN_ALEMBIC_MIGRATIONS` | `True` | — |
| `ENVIRONMENT` | `local` | — |
| `ANALYTICS_ENABLED` | `True` | set `false` — when `ENVIRONMENT` is not `local`, the backend sends product analytics to upstream's PostHog project (the frontend skips PostHog in Gooclaim mode) |
| `METRICS_PORT` / `WORKER_METRICS_PORT` | 9090 / 8888 | — |
| `LOG_LEVEL` | `INFO` | — |

Billing (`STRIPE_*`), Auth0 (`AUTH0_*`) and email (`RESEND_*`) stay unset.

## Compose overrides

`docker/docker-compose.yml` sets these on the backend and worker regardless of `.env`:
`POSTGRES_HOST=postgres`, `REDIS_HOST=redis`, `VESPA_URL=http://vespa`, `VESPA_PORT=8081`,
`TEMPORAL_HOST=temporal`, `TEMPORAL_PORT=7233`, `TEMPORAL_NAMESPACE=default`,
`SVIX_URL=http://svix:8071`, `SVIX_JWT_SECRET=${SVIX_JWT_SECRET}`, `AUTH_ENABLED=false`
(backend), `TEMPORAL_TASK_QUEUE=airweave-sync-queue` (worker), and
`ENVIRONMENT=${ENVIRONMENT:-local}`.

Compose itself interpolates `${...}` — `BACKEND_IMAGE`, `FRONTEND_IMAGE`,
`SVIX_JWT_SECRET`, `POSTGRES_*`, `API_URL` — from the file passed with `--env-file`.
`env_file: ../.env` only feeds the containers. Hence `--env-file ../.env` on every
compose command (see [06-deployment](06-deployment.md)).

## Frontend

| Variable | Where | Notes |
|---|---|---|
| `VITE_GOOCLAIM_MODE` | `frontend/.env.production`, build time | `true` turns on Gooclaim mode (`IS_GOOCLAIM_TENANT` in `src/config/env.ts`). Without it the bundle renders as upstream Airweave |
| `API_URL` | container runtime (`docker-entrypoint.sh` → `config.js`) | Absolute URL or a path starting with `/`; compose default `/api` |
| `ENABLE_AUTH` | container runtime | Compose sets `false` |
