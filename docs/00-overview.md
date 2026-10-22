# 00 — Overview

## What it is

`airweave-fork` is Gooclaim's fork of the open-source Airweave project, run as
**Data Sources**: the place where a tenant (an insurer or TPA) keeps the documents
Gooclaim OS may answer from — policy wordings, regulations, circulars, SOPs.

Two consumers read it, both through `gooclaim-datasources-mcp`:

- **the member-question workflow** in `gooclaim-engine`, which may search only the
  tenant's `members` libraries;
- **Orion** (`gooclaim-orion-api`), the staff coworker, which may search `members` and
  `staff` libraries and cites passages by document and page.

Tenant staff manage libraries in the Data Sources UI (the forked frontend), reached from
the Portal through a short-lived bridge session issued by `gooclaim-auth`.

## What it does

- Keeps libraries (collections) per tenant; the Airweave organization id is the
  Gooclaim tenant id.
- Records who each library answers (`audience`: `members` or `staff`), chosen at creation.
- Accepts uploads (Native Upload) and syncs connected sources (upstream connectors plus
  a Gooclaim AWS S3 connector).
- Converts, chunks, embeds and indexes documents; records page ranges for citations.
- Searches, with a relevance gate on classic search so "nothing relevant" is possible.
- Returns a chunk's full text and, for uploads, the original file — only within the
  caller's tenant.
- Lets a platform admin publish a collection to every tenant (Public).
- Sends sync and connection events to `gooclaim-audit` as webhooks.

## What it does not do

- Compose answers for members or decide what is shown — the engine and the policy gate do.
- Decide which library a caller may search — the datasources MCP does.
- Authenticate users — the front proxy and `gooclaim-auth` do; Auth0 is off.
- Call model providers directly when configured as Gooclaim intends — every call goes
  through the LiteLLM gateway and is billed to the tenant.
- Run Gooclaim's audit ledger — it emits webhooks; `gooclaim-audit` records them.

## Status

Live on dev. The code on `release/dev` is upstream Airweave from 2026-05-18 plus the
Gooclaim changes listed in the README. Upstream has not been merged in since then; see
[gooclaim-fork-rebase](gooclaim-fork-rebase.md).
