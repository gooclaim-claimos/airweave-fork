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

## Deploy (auralixy)
- Runs as Gooclaim "Data Sources"; backend + frontend images `vX.Y.Z-gck.N` via CI. Secrets via
  Azure Key Vault (ESO). SSO/cookie-only auth bridges into the Gooclaim portal session.

## Do not
- Don't rewrite upstream README/docs — record Gooclaim specifics **here**.
- Don't say "Airweave" in user-facing text — it's **Data Sources**.
- Don't commit secrets; `.env` / provider keys stay in AKV.
