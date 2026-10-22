# CLAUDE.md

Guidance for Claude Code in this repository.

## What this repo is

Gooclaim's fork of upstream Airweave (`upstream` remote = airweave-ai/airweave). It runs
as **Data Sources**, the document library of Gooclaim OS: tenants upload or connect
documents; `gooclaim-datasources-mcp` (in `gooclaim-mcp-server`) searches them for the
engine (members) and Orion (staff). In user-facing text it is "Data Sources", never
"Airweave".

- Working branch: **`release/dev`** (the only branch with current code; `develop`,
  `release/uat`, `release/prd` stopped in August 2026, `main` is the May upstream base).
- Base: upstream commit `a9c8b1af7` (2026-05-18). Upstream has not been merged since.
- Push and PR to `gooclaim-claimos/airweave-fork` only. `gh pr create` defaults to the
  upstream parent — always pass `--repo gooclaim-claimos/airweave-fork`.
- Gooclaim code is marked with `Gooclaim` comments. Find it with
  `git log --oneline a9c8b1af7..release/dev` and `grep -rn Gooclaim backend/airweave`.

## Layout

```
backend/airweave/            FastAPI app (Python 3.13, Poetry)
  api/context_resolver.py    auth order (X-API-Key first), org auto-provisioning, master key
  api/deps.py                reads trusted X-Gck-* headers; sets the gateway tenant per request
  api/v1/endpoints/          routes at the root, no /api/v1 prefix; uploads.py is Gooclaim's
  core/gateway_tenant.py     x-litellm-customer-id + "documents" label on every gateway call
  adapters/reranker/relevance_gate.py   classic-search relevance gate (gateway `fast`)
  adapters/llm/anthropic.py  search LLM via ANTHROPIC_BASE_URL / ANTHROPIC_GATEWAY_MODEL
  domains/embedders/dense/openai.py     embeddings via OPENAI_BASE_URL
  domains/ocr/mistral/ocr_client.py     OCR via LLM_GATEWAY_URL /v1/ocr
  domains/ocr/pages.py       page boundaries -> chunk page_start/page_end
  platform/sources/gooclaim_upload.py, s3.py   Gooclaim connectors
  domains/temporal/worker/   Temporal worker (python -m airweave.domains.temporal.worker)
backend/alembic/versions/    0000 upstream baseline + 0001-0004 Gooclaim (run on backend start)
backend/tests/               unit / integration / e2e
backend/airweave/**/tests/   colocated domain tests (second test tree)
frontend/                    React/Vite; .env.production sets VITE_GOOCLAIM_MODE=true
docker/docker-compose.yml    the stack dev runs
vespa/app/                   Vespa app package (fields data_sources_system_metadata_*)
helm/datasources-*/          Kubernetes charts — NOT used by the running environment
fern/ mcp/ connect/ monke/   upstream; do not edit for Gooclaim work
```

## Commands

```bash
# Backend tests — BOTH trees (pytest.ini collects only tests/)
cd backend && poetry run pytest -q tests/unit airweave -n 4
poetry run ruff check . && poetry run ruff format --check .

# Frontend
cd frontend && npm run lint && npm run build

# Local stack — the env file is mandatory
cd docker && docker compose --env-file ../.env up -d
docker compose --env-file ../.env --profile frontend up -d frontend
```

`backend/conftest.py` sets the env `Settings` needs; no `.env` for tests. Compare any
failure with the same run on the base commit before calling it pre-existing.
There is no server CI for `release/dev` (`gooclaim-ci.yml` triggers on `develop` only):
run the checks locally before pushing.

## Non-negotiable rules

1. **Organization id = Gooclaim tenant id.** Orgs are auto-created from
   `X-Organization-ID` (`EXTERNAL_ORG_ID_PROVISIONING`). Never map or re-key them.
2. **Every AI call goes through the LiteLLM gateway and names the tenant.** A new AI
   client whose base URL is the gateway gets `event_hooks=tenant_event_hooks()`. Never
   add a provider key or a direct provider call. Providers with a key set
   (Together, Groq, Cerebras, Mistral, Cohere, Azure DI) bypass the gateway — keep them unset.
3. **Trusted headers come only from the front proxy.** `X-Organization-ID`, `X-Gck-Platform-Admin`,
   `X-Gck-User-Email`, `X-Gck-Return-Url`, `X-Gck-Tenant-Name` are believed as sent.
   Do not add a route that acts on them without the platform-admin check where a
   cross-tenant action is possible.
4. **Platform-admin gates stay:** org create/delete, `/admin/*`, collection visibility.
5. **`collection.audience` is required and fixed** (`members` / `staff`). No default.
   The MCP enforces who may search which library.
6. **Upload buckets:** only via `bucket_dir(organization_id, bucket)`
   (`STORAGE_PATH/uploads/{org}/{bucket}`). Never read a path an entity or config names.
   Never hand the original to the pipeline (it deletes `local_path` after a batch).
7. **Relevance gate fails closed.** If it errors, classic search errors; never return
   ungated results.
8. **No query, passage or file content in logs** — a member's question can carry PHI.
9. **`api_key.is_master`** is set only in the database, never through an API.
10. **Compose:** backend and worker both mount `local_storage` and both need
    `extra_hosts: host.docker.internal` (the worker embeds). Keep both.

## Deploy (dev)

AWS EC2, `docker compose` from `docker/`. Backend and worker bind-mount `../backend:/app`:
deploy = copy committed files (`git archive <sha> ...`) + recreate `backend temporal-worker`
with `--env-file ../.env`. Without it compose runs the **upstream** image with an empty
`SVIX_JWT_SECRET` and the backend crash-loops. The box's compose and `.env` differ from
the repo — never copy the repo compose over them. Frontend = image in `FRONTEND_IMAGE`.
See `docs/06-deployment.md`.

## Do not touch without discussion

- `context_resolver.py` auth order and the provisioning / membership skip
- `gateway_tenant.py` header names (the LiteLLM spend contract shared with `gooclaim_shared.ai_usage`)
- Alembic `0001`–`0004` (new Gooclaim revisions continue the chain; check upstream's numbering first)
- Vespa schema field names (`data_sources_system_metadata_*`) — renaming means reindexing
- Upstream code outside Gooclaim changes: keep diffs small so rebases stay possible

## Docs

`README.md` (overview), `docs/` (Gooclaim-specific set; index `docs/README.md`),
`docs/gooclaim-fork-rebase.md` (upstream rebase runbook). Upstream docs live in `fern/`
and at docs.airweave.ai — do not rewrite them. `GOOCLAIM-FORK.md` is older and partly
stale; `README.md` and `docs/` win where they disagree.
