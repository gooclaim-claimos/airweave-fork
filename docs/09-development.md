# 09 — Development

## Branches and remotes

| Remote | Repository |
|---|---|
| `origin` | `gooclaim-claimos/airweave-fork` — the only push and PR target |
| `upstream` | `airweave-ai/airweave` — fetch only |

| Branch | State |
|---|---|
| `release/dev` | Default and working branch; all current Gooclaim code |
| `release/uat`, `release/prd`, `develop` | Stopped at 2026-08-01; behind `release/dev` |
| `main` | Upstream base (2026-05-18) plus the first two Gooclaim patches |

Flow for changes: `feature|fix|chore|docs/<x>` → `release/dev` → `release/uat` → `main`
→ `release/prd`. Today only `release/dev` is promoted to.

`gh pr create` defaults to the upstream parent. Always pass
`--repo gooclaim-claimos/airweave-fork`. Gooclaim changes are never contributed upstream.

## Local setup

```bash
cd backend && poetry install          # Python 3.13
cd ../frontend && npm install
cd ../docker && docker compose --env-file ../.env up -d
```

Run the backend outside Docker against the compose services:
`poetry run uvicorn airweave.main:app --host 0.0.0.0 --port 8001 --reload` (with
`POSTGRES_HOST=localhost` etc.). Frontend dev server: `npm run dev` (port 8080).

## Making a Gooclaim change

1. **Keep the diff small and marked.** Put a `# Gooclaim:` comment on every change to an
   upstream file, saying why. Prefer a new module (`core/gateway_tenant.py`,
   `platform/sources/gooclaim_upload.py`, `adapters/reranker/relevance_gate.py`) over
   rewriting upstream code. Every changed upstream line is a future rebase conflict.
2. **A new AI call** goes to the gateway: base URL from env, `event_hooks=tenant_event_hooks()`
   only when that base URL is set, the gateway alias rather than a vendor model name.
   Add a test that inspects the outgoing request.
3. **A new route that acts across tenants** checks `ctx.auth_metadata["platform_admin"]`
   when `EXTERNAL_ORG_ID_PROVISIONING` is on.
4. **A schema change** is a new Alembic revision continuing the Gooclaim chain
   (`0005`, `down_revision = '0004'`). Check upstream's `backend/alembic/versions/` first:
   upstream's history starts at `0000_baseline`, and a future upstream `0001` would
   collide with ours.
5. **A Vespa field** is added to `vespa/app/schemas/*.sd` (and the Helm copy if it is
   ever revived). Adding is safe; renaming needs a reindex.
6. **Frontend text** says "Data Sources", never "Airweave". Gate Gooclaim-only UI on
   `IS_GOOCLAIM_TENANT`.
7. Run both test trees and ruff ([08-testing](08-testing.md)); run `npm run lint` and
   `npm run build` for frontend changes.

## Code style

Upstream's: ruff (100-character lines, Google docstrings, double quotes), async I/O,
typed signatures; on the frontend, TailwindCSS with `cn()`, shared types in
`src/types/index.ts`, Zustand for global state, `@/` = `./src`. Never use `random.*` for
security values (ruff S311) or `Math.random()` in the frontend.

## Bringing in upstream

See [gooclaim-fork-rebase](gooclaim-fork-rebase.md).
