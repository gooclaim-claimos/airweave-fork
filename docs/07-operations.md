# 07 — Operations

## Health

| Check | Where |
|---|---|
| `GET /health/ready` | backend; compose healthcheck (503 when a critical probe fails; `HEALTH_CRITICAL_PROBES` defaults to `postgres`) |
| `GET /health/live`, `GET /health` | backend |
| `/health`, `/drain` on `WORKER_METRICS_PORT` (8888) | worker control server, inside the container |
| `GET /state/v1/health` on 19071 | Vespa config server |
| Temporal UI on 8088 | sync workflows (task queue `airweave-sync-queue`) |

## Logs

```bash
docker logs --tail 200 airweave-backend
docker logs --tail 200 airweave-temporal-worker
```

API log lines are bound to `request_id`, `organization_id`, `organization_name`,
`auth_method` and, when present, `user_id` / `user_email` (on browser requests this is
the shared system user, not the real caller). The relevance gate and
upload code never log queries, passages or file content. An organization auto-created
on first use logs `airweave.gooclaim_bridge: auto-provisioned org <id>`.

## Metrics

Prometheus on `METRICS_PORT` (9090, published by compose): HTTP, DB pool and agentic
search metrics. The worker exposes Temporal SDK metrics on `TEMPORAL_SDK_METRICS_PORT`.

## AI spend

Every gateway call is labelled `feature:documents` and carries the tenant in
`x-litellm-customer-id`, so LiteLLM's spend logs show Data Sources cost per tenant. A
call with no organization in context (a startup probe, a script) is billed to the
gateway key only.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| Backend crash-loops after a recreate; image is `ghcr.io/airweave-ai/...` | Compose run without `--env-file ../.env` | Recreate with the env file; check `alembic_version` afterwards |
| Native Upload sync "completes" with only the connection entity, 0 files | Worker does not mount `local_storage` | Keep the `../local_storage` mount on `temporal-worker` |
| Every sync fails with "OpenAI connection failed" | Worker cannot resolve the gateway host | Keep `extra_hosts: host.docker.internal:host-gateway` on the worker |
| Requests fail with "missing an 'http://' or 'https://' protocol" | An env var like `OPENAI_BASE_URL=` present but empty in an older build | Current code treats empty as unset; remove the empty line |
| Upload rejected with 413 | Body over `API_REQUEST_BODY_SIZE_LIMIT` | Default is 50 MiB; do not lower it below the UI cap |
| Upload rejected with 415 | Extension not in the Native Upload set | See [03-apis](03-apis.md) |
| Classic/agentic search 503 | No provider in `LLM_FALLBACK_CHAIN` has a key | Set `ANTHROPIC_API_KEY` (the gateway key) |
| Classic search fails while instant search works | Relevance gate call failed (gateway down, alias `fast` missing) | Fix the gateway; the gate fails closed by design |
| OCR sync error "LLM_GATEWAY_API_KEY required" | `LLM_GATEWAY_URL` set without the key | Set both |
| A cited passage's original returns 404 | Not a native upload, or the original is no longer in the bucket | Re-upload the document |
| No syncs run, no errors | `temporal-worker` stopped | Start it; it restarts `unless-stopped` |
| An organization appears with a `tenant-xxxxxxxx` name | Auto-provisioned without `X-Gck-Tenant-Name` | Rename in the database; check the proxy forwards the header |

## Routine tasks

- **Make a collection Public:** platform admin, Data Sources UI collection page, or
  `PATCH /collections/{readable_id}/visibility`.
- **Mark an API key as master:** only in the database (`api_key.is_master = true`); no API
  can set it. Keep the set of master keys minimal.
- **Remove a tenant:** deleting its organization (platform admin) goes through upstream's
  organization delete, which does not touch Native Upload files; remove
  `local_storage/uploads/{organization_id}/` from disk separately.
