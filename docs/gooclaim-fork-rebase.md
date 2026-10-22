# Bringing in a newer upstream

This fork (`gooclaim-claimos/airweave-fork`) carries Gooclaim changes on top of
`airweave-ai/airweave`. This runbook covers taking a newer upstream into `release/dev`.

## Where things stand

- Base: upstream commit `a9c8b1af7` (upstream PR #1787, 2026-05-18).
- On top: 94 Gooclaim commits on `release/dev` (`git log --oneline a9c8b1af7..release/dev`),
  touching about 370 files. Upstream has not been merged in since the base.
- Upstream keeps moving. One upstream change already relevant to Gooclaim: PR #1803 made
  the Mistral SDK base URL configurable, which overlaps with the fork's own gateway
  routing for OCR.

The Gooclaim changes are summarised in the README ("How It Differs From Upstream").
They are no longer the two small patches this runbook once described (an Azure OpenAI
`base_url` and org auto-provisioning). Azure OpenAI is not used: every AI call goes to
the LiteLLM gateway.

## Method: merge, do not rebase

`release/dev` is pushed and deployed. Rebasing 94 commits would rewrite its history and
need a force-push. Merge upstream into a branch instead:

```bash
git fetch upstream
git log --oneline release/dev..upstream/main | wc -l      # how far behind
git checkout -b chore/upstream-sync-<date> release/dev
git merge upstream/main                                    # or a release tag
```

Resolve conflicts, verify (below), then open a PR to `release/dev` with
`gh pr create --repo gooclaim-claimos/airweave-fork`. Never push to or open a PR against
upstream.

To limit the size of one sync, merge an upstream release tag rather than `main`.

## Where conflicts will be

| Area | Why | Files |
|---|---|---|
| Vespa field names | Gooclaim renamed `airweave_system_metadata_*` to `data_sources_system_metadata_*` everywhere. Any upstream code or schema line using the old names conflicts or, worse, merges cleanly and reads a field that no longer exists | `vespa/app/schemas/*.sd`, `platform/destinations/vespa/*`, `domains/search/**`, `schemas/search_v2.py` |
| Auth and tenancy | Auth order, provisioning, master key, platform-admin gates | `api/context_resolver.py`, `api/deps.py`, `api/context.py`, `endpoints/{organizations,admin,users,collections}.py` |
| Search | Public collections in one query, browse-only exclusion, relevance gate wiring, page fields | `domains/search/**`, `core/container/factory.py` |
| AI clients | Gateway base URLs and the tenant hook | `domains/embedders/dense/openai.py`, `adapters/llm/anthropic.py`, `search/providers/openai.py`, `domains/ocr/mistral/*`, `platform/chunkers/semantic.py` |
| Collections | `audience`, `is_public` | `models/collection.py`, `schemas/collection.py`, `crud/crud_collection.py`, `domains/collections/**` |
| Settings | Gooclaim fields and the 50 MiB body limit | `core/config/settings.py` |
| Compose | `extra_hosts`, `local_storage` on the worker, restart policies | `docker/docker-compose.yml` |
| Frontend | Gooclaim mode gates, no Bearer header, Native Upload view | `frontend/src/lib/api.ts`, `App.tsx`, `DashboardLayout.tsx`, `UserProfileDropdown.tsx`, `CollectionDetailView.tsx`, creation views |

Gooclaim-only files (`core/gateway_tenant.py`, `adapters/reranker/relevance_gate.py`,
`platform/sources/gooclaim_upload.py`, `platform/sources/s3.py`,
`api/v1/endpoints/uploads.py`, `domains/ocr/pages.py`) do not conflict but may break if
upstream changes the interfaces they use.

## After the merge, before the PR

1. **Migrations.** Upstream's history starts at `0000_baseline`; Gooclaim's continues
   `0001`–`0004`. If upstream added revisions, they will have a `down_revision` of
   `0000` (or later) and the chain forks. Re-point upstream's new revisions after `0004`
   (or ours after theirs) so there is exactly one head:
   `cd backend && poetry run alembic heads`. Never renumber a revision that has run on dev.
2. **Old field names.** `grep -rn airweave_system_metadata backend vespa` must return
   nothing.
3. **New AI calls.** Diff upstream for new model clients or new provider calls
   (`git diff a9c8b1af7 upstream/main -- backend | grep -n -E 'AsyncOpenAI|AsyncAnthropic|Mistral\(|httpx.AsyncClient'`).
   Each one that Gooclaim will use must go through the gateway with `tenant_event_hooks()`.
   Check whether upstream's own base-URL support (for example PR #1803) can replace a
   Gooclaim patch; if it can, take upstream's and drop ours.
4. **New settings.** Check new `Settings` fields with risky defaults (anything that
   enables a provider, analytics or an external call by default).
5. **New routes.** Any new route that can act across organizations needs the
   platform-admin gate in provisioning mode.
6. **Frontend.** New upstream screens must be gated on `IS_GOOCLAIM_TENANT` if they expose
   billing, members, API keys or the word "Airweave".
7. **Tests.** `cd backend && poetry run pytest -q tests/unit airweave -n 4`, compared
   with the same run on `release/dev`; `ruff check` and `ruff format --check`;
   `cd frontend && npm run lint && npm run build`.
8. **Compose.** Merge upstream compose changes into the repo file, keep the Gooclaim
   lines, and apply the same change by hand to the live compose file on the instance
   (never copy the repo file over it).

## Deploying the result

As any backend change ([06-deployment](06-deployment.md)): copy the committed files,
recreate `backend` and `temporal-worker` with `--env-file ../.env`, let Alembic run, and
redeploy `vespa/app` if the schema changed. If upstream changed backend dependencies,
build a new backend image first. Rebuild the frontend image if `frontend/` changed.
