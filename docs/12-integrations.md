# 12 — Integrations

How Data Sources connects to the rest of Gooclaim OS. Each row names the code on the
other side so the contract can be checked there.

| Peer | Direction | Contract |
|---|---|---|
| `gooclaim-auth` | Portal → auth → proxy → Data Sources | Bridge session for the UI |
| `gooclaim-datasources-mcp` (`gooclaim-mcp-server`) | MCP → Data Sources | Search, chunk content, originals |
| `gooclaim-engine`, `gooclaim-orion-api` | via the MCP only | Member answers, staff answers |
| LiteLLM gateway | Data Sources → gateway | Every AI call, billed per tenant |
| `gooclaim-audit` | Data Sources (Svix) → audit | Sync and connection webhooks |

## gooclaim-auth — the UI bridge

1. A Portal user opens Data Sources. Portal calls `POST /v1/auth/airweave-sso-mint` on
   `gooclaim-auth`, which issues a short-lived bridge token (default 15 minutes,
   `airweave_bridge_token_ttl`) in the `gooclaim_airweave_bridge` cookie.
2. Every UI request passes the front proxy, which calls
   `GET /v1/auth/airweave-verify`. On success that returns `X-Organization-Id` (the
   tenant id), `X-Gck-Tenant-Id`, `X-Gck-User-Id`, `X-Gck-Tenant-Name`,
   `X-Gck-User-Email`, `X-Gck-Platform-Admin` and `X-Gck-Return-Url`; on failure 401.
3. The proxy forwards those headers to the backend
   ([11-security](11-security.md) explains why it must overwrite them).

The UI never sends an `Authorization: Bearer` header: `gooclaim-auth` would read it
before the cookie and reject it. `frontend/src/lib/api.ts` deliberately omits it, and
also omits `X-Organization-ID`, which the proxy supplies.

Code: `gooclaim-auth/src/gooclaim_auth/routes/auth.py` (`airweave_sso_mint`,
`airweave_verify`), `gooclaim-auth/src/gooclaim_auth/config.py` (`airweave_bridge_*`).

## gooclaim-datasources-mcp — the service path

The MCP is the only service that calls the backend directly. It sends its master API
key as `X-API-Key` and the tenant as `X-Organization-Id` on every call. It:

- lists collections and reads each one's `audience` to decide which libraries a caller
  may search (`members` for the engine, `members` + `staff` for Orion);
- fans a query out to `POST /collections/{readable_id}/search/classic` per library and
  merges the results, keeping `page_start` / `page_end` for citations;
- treats an empty result as a real answer ("not in your documents") and a failure of
  every collection as an outage;
- fetches `GET /entities/{id}/content` and `GET /entities/{id}/original` to open a cited
  document.

Routes: [03-apis](03-apis.md). Code:
`gooclaim-mcp-server/services/datasources/src/gooclaim_datasources_mcp/client.py`.

`gooclaim-engine` (`clients/datasources_client.py`) and `gooclaim-orion-api`
(`library.py`) call the MCP's `search_knowledge` tool; neither calls this service.

## LiteLLM gateway

| Call | Endpoint on the gateway | Model |
|---|---|---|
| Embeddings | OpenAI-compatible, via `OPENAI_BASE_URL` | the configured dense embedder's model |
| Search LLM | Anthropic-compatible `/v1/messages`, via `ANTHROPIC_BASE_URL` | `ANTHROPIC_GATEWAY_MODEL` (`smart`) |
| OCR | `POST {LLM_GATEWAY_URL}/v1/ocr`, document inline as a data URL | `mistral-ocr-latest` |
| Relevance gate | OpenAI-compatible chat via `LLM_GATEWAY_URL` | `fast` |

Every call carries `x-litellm-customer-id` (organization id = tenant id),
`x-litellm-spend-logs-metadata: {"feature":"documents"}` and
`x-litellm-tags: feature:documents` (`backend/airweave/core/gateway_tenant.py`). The
header names match the `gooclaim_shared.ai_usage` contract; the fork does not depend on
`gooclaim-shared`, so they are written out here and must be kept in step by hand.

## gooclaim-audit — webhooks

Svix (bundled in compose) delivers upstream webhook events to subscribed endpoints.
`gooclaim-audit` receives them at `POST /v1/audit/airweave-webhook`, verifies the Svix
signature (`airweave_webhook_secret`, maximum clock skew 300 s) and maps:

| Webhook `type` | Audit event |
|---|---|
| `sync_job.completed` | `DATA_SOURCES_SYNC_COMPLETED` |
| `sync_job.failed` | `DATA_SOURCES_SYNC_FAILED` |
| `connection.created` | `DATA_SOURCES_SOURCE_CONNECTED` |
| `connection.deleted` | `DATA_SOURCES_SOURCE_DISCONNECTED` |

The event's `organization_id` is the tenant id; an event without one is rejected with 422.
The subscription is created through upstream's webhooks API (`/webhooks`).

Code: `gooclaim-audit/src/gooclaim_audit/api/airweave_webhook.py`.

## Not integrated

`gooclaim-tenant-config` has a knowledge-sources router that is parked; document
ingestion is this service's job. The upstream MCP server in `mcp/` and the Connect widget
in `connect/` are not used by Gooclaim.
