# 03 — APIs

Routes are mounted at the root of the backend (`backend/airweave/api/v1/api.py`); there
is no `/api/v1` prefix. Interactive docs: `GET /docs` on the backend. This page covers
only what Gooclaim uses or added. Everything else is upstream:
<https://docs.airweave.ai>.

## Authentication and tenant headers

| Header | Sent by | Meaning |
|---|---|---|
| `X-API-Key` | services | API key. Checked before anything else. A master key (`is_master`) may act for any organization |
| `X-Organization-ID` | services, front proxy | Tenant UUID. Unknown UUIDs auto-create the organization (provisioning mode) |
| `X-Gck-Tenant-Name` | front proxy | Name for an auto-created organization |
| `X-Gck-User-Email` | front proxy | Real caller, shown in the UI and stored as "created by" |
| `X-Gck-Platform-Admin` | front proxy | `true` for a Gooclaim platform admin; unlocks the gates below |
| `X-Gck-Return-Url` | front proxy | Where the UI's "Back to portal" goes |

A request with no `X-API-Key` runs as the system superuser for the named organization
(see [11-security](11-security.md)).

## Used by `gooclaim-datasources-mcp`

Source: `gooclaim-mcp-server/services/datasources/.../client.py`.

| Method & path | Purpose |
|---|---|
| `GET /collections` | The tenant's collections plus Public ones; the MCP reads `audience` to decide which libraries a caller may search |
| `POST /collections/{readable_id}/search/classic` | Body `{"query": str, "limit": int}`. Results carry `data_sources_system_metadata` (with `page_start` / `page_end`), `textual_representation`, `entity_id`, `name`, `web_url`. May return no results |
| `POST /collections/{readable_id}/search/browse` | Browse a collection |
| `GET /entities/{entity_id}/content` | `{entity_id, schema, fields}` for one chunk. 404 unless the chunk is in a collection the caller may read |
| `GET /entities/{entity_id}/original` | Original file of a native upload, read from the caller's own bucket; `Cache-Control: no-store`, `nosniff`. 404 for other sources or a missing file |
| `GET /sources` | Connector catalogue |
| `GET /source-connections` | The tenant's connections |
| `GET /files/{entity_id}` · `GET /files/{entity_id}/content` | File metadata / content |
| `GET /entity-counts/syncs/{sync_id}/total-count` | Entities indexed by a sync |

The engine and Orion do not call the backend; they call the MCP.

## Added by Gooclaim

### Native Upload — `backend/airweave/api/v1/endpoints/uploads.py`

| Method & path | Notes |
|---|---|
| `POST /uploads/{connection_id}` | Multipart `file` (+ optional `description`). ≤ 50 MiB. Extensions: `.pdf .docx .doc .pptx .txt .md .html .htm .csv .json`, otherwise 415. Writes the file and a `.gooclaim.json` sidecar into the caller's bucket `connection_id` |
| `GET /uploads/{connection_id}` | Lists the bucket's uploads |
| `POST /uploads/{connection_id}/commit` | Form: `collection_name` (4–64), optional `description`, `audience` (`members` / `staff`; required when the collection does not exist yet, must match when it does). Creates or reuses the collection (`readable_id` = `connection_id`) and its `gooclaim_upload` connection, then starts a sync |

`connection_id` must match `[a-zA-Z0-9_-]{1,128}`.

### Collections

| Method & path | Notes |
|---|---|
| `POST /collections` | `audience` is **required** (`members` / `staff`); there is no default |
| `PATCH /collections/{readable_id}/visibility` | `{"is_public": bool}`. Platform admin only when provisioning mode is on (403 otherwise) |

### Entities

`GET /entities/{entity_id}/content` and `GET /entities/{entity_id}/original` (above).

### Changed behaviour

| Route | Gooclaim change |
|---|---|
| `GET /users/me` | Adds `is_platform_admin` and `return_url`; replaces the email with `X-Gck-User-Email` when present |
| `GET /users/me/organizations` | Only the current organization (provisioning mode) |
| `POST /organizations`, `DELETE /organizations/{id}` | Platform admin only (provisioning mode) |
| `/admin/*` | Platform admin only (provisioning mode); otherwise 403 "Admin endpoints are disabled" |
| `POST /collections/{id}/search/browse` | No longer behind the upstream `COLLECTION_BROWSE` feature flag |
| `GET /files/*` | Upstream's hard-coded single-customer gate removed |

## Outbound

Svix delivers upstream webhook events (`sync_job.completed`, `sync_job.failed`,
`connection.created`, `connection.deleted`, …) to subscribed endpoints. Gooclaim's
receiver is `POST /v1/audit/airweave-webhook` in `gooclaim-audit`, which verifies the
Svix signature and maps the four events above to `DATA_SOURCES_*` audit events. See
[12-integrations](12-integrations.md).
