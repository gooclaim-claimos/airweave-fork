# 11 — Security

## Trust boundary

Gooclaim runs the backend with `AUTH_ENABLED=false` (forced by compose) and
`EXTERNAL_ORG_ID_PROVISIONING=true`. In that mode the backend does not authenticate
browser users. `backend/airweave/api/context_resolver.py` resolves every request as
follows:

1. `X-API-Key` present → the key is validated (403 if invalid or expired). This happens
   before the `AUTH_ENABLED` check.
2. No key and `AUTH_ENABLED=false` → the request runs as the **system superuser**.
3. The organization is taken from `X-Organization-ID`; an unknown UUID creates the
   organization on the spot.
4. For system-auth requests in provisioning mode the membership check is skipped.

So **anyone who can reach the backend port can act as any tenant**, and can claim
platform admin by sending `X-Gck-Platform-Admin: true`. The protection lies entirely
outside this repository:

- the front proxy must check the Gooclaim session (`gooclaim-auth`
  `GET /v1/auth/airweave-verify`) on every request, and **overwrite** — not append to —
  `X-Organization-ID`, `X-Gck-Platform-Admin`, `X-Gck-User-Email`, `X-Gck-Tenant-Name`
  and `X-Gck-Return-Url` with the values from that check;
- the backend port (8001), the metrics port (9090) and the other published ports must not
  be reachable except from the proxy and the internal services that need them.

The proxy configuration and the network rules are not in this repository; check them
whenever either changes. Compose publishes every port on all interfaces by default.

## Trusted headers

| Header | Effect | Read in |
|---|---|---|
| `X-Organization-ID` | Tenant scope of the request | `api/deps.py`, `context_resolver.py` |
| `X-Gck-Platform-Admin: true` | Unlocks org create/delete, `/admin/*`, collection visibility | `api/deps.py`, `endpoints/organizations.py`, `endpoints/admin.py`, `endpoints/collections.py` |
| `X-Gck-User-Email` | Shown as the user; stored as "created by" | `api/deps.py`, `api/context.py`, `endpoints/users.py` |
| `X-Gck-Tenant-Name` | Name of an auto-created organization | `context_resolver.py` |
| `X-Gck-Return-Url` | Target of "Back to portal" | `endpoints/users.py` |

## Master API key

`api_key.is_master` (migration `0002`) lets one key act for **any** organization named in
`X-Organization-ID`. It is used by `gooclaim-datasources-mcp`, which serves every tenant.
No API can set the flag; it is set directly in the database. A leaked master key exposes
every tenant's documents: keep the set minimal, rotate on suspicion, and give it only to
services that set `X-Organization-ID` from a verified token.

## Tenant isolation inside the backend

- **Collections:** reads are scoped to the caller's organization, plus Public
  collections; writes are never granted by Public (`crud/crud_collection.py`).
- **Chunks:** `GET /entities/{id}/content` and `/original` return a chunk only if it is in a
  collection the caller may read; another tenant's id reads as "not found"
  (`endpoints/entities.py`).
- **Upload buckets:** `STORAGE_PATH/uploads/{organization_id}/{bucket}`, bucket names
  limited to `[a-zA-Z0-9_-]{1,128}` (`platform/sources/gooclaim_upload.py`).
  `check_config` refuses any directory that is not one of the running organization's
  buckets; `/original` reads only from the caller's own bucket, never from a path the
  index names.
- **Organization list:** `/users/me/organizations` returns only the current organization.
- **Libraries:** `collection.audience` records `members` / `staff`; the datasources MCP,
  not this service, enforces which callers may search staff libraries.

## AI calls and data leaving the service

- With the gateway variables set, embeddings, OCR, the search LLM and the relevance gate
  go to the LiteLLM gateway only, with the tenant id in `x-litellm-customer-id`. Provider
  keys must stay unset (see [05-configuration](05-configuration.md)); a key that is set
  sends documents to that provider directly.
- OCR sends the whole document inline to the gateway's `/v1/ocr`.
- The backend's product analytics go to upstream's PostHog project whenever
  `ANALYTICS_ENABLED` is true and `ENVIRONMENT` is not `local`. Set
  `ANALYTICS_ENABLED=false`. The frontend skips PostHog in Gooclaim mode.

## Logging and PHI

The relevance gate and the upload routes never log a query, a passage or document content.
API logs do carry `organization_name`, the system user's `user_email` on browser
requests, and, on every uncached API-key request, the key's `created_by_email` and the
client IP. `X-Gck-User-Email` is stored in `created_by` / `modified_by` fields
(`ApiContext.tracking_email`).

## Secrets

Secrets reach the containers as environment variables from `.env` on the instance.
`ENCRYPTION_KEY` encrypts stored source credentials (for example the S3 connector's
keys). Never commit `.env`.
