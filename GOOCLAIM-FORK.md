# GOOCLAIM — Fork Notes

`airweave-fork` is a **fork** of the upstream [airweave-ai/airweave](https://github.com/airweave-ai/airweave),
deployed as **Gooclaim "Data Sources"** (the pilot knowledge / connector-sync layer at
`sources.dev.gooclaim.com`). Upstream code + docs are unchanged; this file records the
Gooclaim-specific conventions layered on top.

> In all user-facing text this is **"Data Sources"**, never "Airweave".

## Status
**Live (pilot).** v1.0 pilot uses Airweave (battle-tested) to derisk the knowledge layer; the
in-house `gooclaim-knowledge` pipeline is parked for post-pilot. Our customizations (Sources
rebrand, cookie-only auth / SSO bridge, "Back to portal", platform-admin dashboard gating,
Azure/OpenAI base_url support) live on **`develop`** and ship as `datasources-backend` /
`datasources-frontend` (`vX.Y.Z-gck.N` images).

## Branch strategy (Gooclaim)
> **Correction (2026-09-10, founder):** `develop` is not actually used anymore.
> `release/dev` is the real working branch — treat it as the source of truth
> below, not `develop`.
- **`main`** — upstream mirror. Sync upstream here; do NOT put Gooclaim changes on main.
- **`develop`** — Gooclaim "Data Sources" customizations (the live source; CI builds `-gck.N` images).
- **`release/dev`** (default) — promotion branch off develop. Maintainer direct-push; others PR + review.
- **`release/uat` / `release/prd`** — promotion branches (PR + review/approval).

Flow for our changes: `feature/fix/chore/docs/* → release/dev → release/uat → release/prd`.
Pull upstream into `main`, then merge `main → develop` to adopt upstream updates.

## Push / PR target (hard rule)
**All push + PR operations target `gooclaim-claimos/airweave-fork` ONLY.** Never push to or open a
PR against upstream `airweave-ai/airweave` — Gooclaim rebrand work must not leak into the OSS
project. `gh pr create` defaults to the upstream parent — always pass
`--repo gooclaim-claimos/airweave-fork` explicitly.

## Public/Private collections (shared knowledge)
A Collection can be **Public** (`is_public=True`) — readable by every organization, not
just its owner. Built for Console-curated shared knowledge (e.g. regulations/compliance
docs) that every tenant's search should draw on alongside their own private data.

- **Toggle**: `PATCH /collections/{readable_id}/visibility` — platform admin only
  (`X-Gck-Platform-Admin`, same gate as org create/delete). UI control lives in
  `CollectionDetailView.tsx`, visible only when `IS_GOOCLAIM_TENANT && user.is_platform_admin`;
  a regular tenant session never sees it, only a read-only "Public" badge if the collection
  they're viewing happens to be one.
- **Read access**: `crud_collection.py`'s `get`/`get_by_readable_id`/`get_multi`/`count` all
  OR in `is_public=True` alongside the normal org-scope filter — a Public collection is
  visible cross-org, a Private one is not. Write paths (create/update/remove) are unchanged;
  visibility does not grant write access.
- **Search**: a search against your own collection also ranks every Public collection in the
  *same* Vespa call (`VespaVectorDB._build_collection_clause` ORs the collection IDs) rather
  than merging separately-scored searches — ranking stays consistent. Wired through all three
  search tiers (classic, instant, agentic's SEARCH tool); the agentic READ/COUNT/navigate
  tools deliberately stay single-collection, unchanged.
- **Model note**: `Collection.is_public` needs BOTH `default=False` (Python-side) and
  `server_default` (DB-side) — server_default alone leaves it `None` on an unflushed/unrefreshed
  ORM object, which then fails `CollectionRecord`'s (non-Optional) bool validation. The schema
  also has a `mode="before"` validator coercing `None → False` as a second line of defense for
  any construction path that never touches the DB at all (several existing tests do this).

## Deploy (auralixy)
- Runs as Gooclaim "Data Sources"; backend + frontend images `vX.Y.Z-gck.N` via CI. Secrets via
  Azure Key Vault (ESO). SSO/cookie-only auth bridges into the Gooclaim portal session.

## Do not
- Don't rewrite upstream README/docs — record Gooclaim specifics **here**.
- Don't say "Airweave" in user-facing text — it's **Data Sources**.
- Don't commit secrets; `.env` / provider keys stay in AKV.
