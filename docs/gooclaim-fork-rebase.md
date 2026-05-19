# Gooclaim fork — upstream rebase runbook

This fork (`gooclaim-claimos/airweave-fork`) carries Gooclaim patches on
top of `airweave-ai/airweave`:

1. **Azure OpenAI routing** via `OPENAI_BASE_URL` env var
2. **External-org auto-provision** for the gooclaim ↔ Airweave bridge

## The patches (small, focused)

**Patch 1 — Azure OpenAI (PR #1, merged):**
- `backend/airweave/domains/embedders/dense/openai.py` — adds
  `base_url=os.getenv("OPENAI_BASE_URL")` to `AsyncOpenAI(...)`
- `backend/airweave/search/providers/openai.py` — same for LLM provider
- `.env.example` — documents `OPENAI_BASE_URL`

**Patch 2 — External-org provisioning (PR #2, merged):**
- `backend/airweave/core/config/settings.py` — adds
  `EXTERNAL_ORG_ID_PROVISIONING: bool = False`
- `backend/airweave/api/context_resolver.py` — auto-creates org when
  `X-Organization-ID` header carries an unknown UUID (gated behind
  `AUTH_ENABLED=False + EXTERNAL_ORG_ID_PROVISIONING=True`); skips
  membership check in this mode (nginx-auth-request is the trust
  boundary)

Total: ~90 lines across 4 files.

## Why this patch

Upstream Airweave instantiates `AsyncOpenAI(api_key=...)` without
`base_url`, hardcoding OpenAI direct. Gooclaim's stack is locked to
**Azure OpenAI** (centralindia region) per IRDAI / DPDP requirements
(memory: `project_irdai_binding_constraint.md`). The patch reads
`OPENAI_BASE_URL` from env so the same `openai` SDK client can route
through Azure OpenAI without further code changes.

## Branches

| Branch | Role |
|--------|------|
| `develop` | **Default branch.** Gooclaim PR target. CI runs on push/PR via `.github/workflows/gooclaim-ci.yml`. |
| `main` | Stable. Built into our Docker image (`ghcr.io/gooclaim-claimos/airweave-backend:vX.Y.Z-gck.N`). Promote from `develop` once green. |
| `claude/s5-*`, feature branches | PR-only branches → develop. |

Upstream sync flow:
```
upstream/main → fork/main (rebase + replay our patches)
fork/main     → fork/develop (FF sync so develop stays current)
```

## Rebase against new upstream release

```bash
# 1. Fetch latest upstream
git fetch upstream

# 2. Check what's new (e.g. tag v0.9.70)
git log --oneline upstream/main | head -20

# 3. Rebase our patch onto the new release
git checkout gooclaim-azure-openai
git rebase upstream/v0.9.70

# 4. Resolve any conflicts in the 3 files above. Almost never conflicts
#    because the upstream files rarely change in the patched lines.

# 5. Re-tag our image
docker build -t ghcr.io/gooclaim-claimos/airweave-backend:v0.9.70-gck.1 \
  -f backend/Dockerfile backend/
docker push ghcr.io/gooclaim-claimos/airweave-backend:v0.9.70-gck.1

# 6. Bump image tag in gooclaim-infra Helm values
#    helm/airweave/values-dev.yaml → BACKEND_IMAGE
```

## Tagging convention

Our images are tagged as `<upstream-version>-gck.<patch-revision>`:
- `v0.9.69-gck.1` — initial patch on upstream v0.9.69
- `v0.9.70-gck.1` — same patch rebased onto v0.9.70
- `v0.9.70-gck.2` — additional patch added (e.g. SSO support)

## When NOT to rebase

If upstream changes the embedder file (`dense/openai.py`) substantially,
review carefully before rebasing. Our patch is just a `base_url=` param
addition — usually safe. If they refactor to a different client class,
re-think the patch.

## Verification after rebase

```bash
# Build image
docker build -t airweave-backend-test -f backend/Dockerfile backend/

# Run smoke test with Azure OpenAI
docker run --rm \
  -e OPENAI_BASE_URL=https://<resource>.openai.azure.com/openai/v1/ \
  -e OPENAI_API_KEY=<azure-key> \
  -e DENSE_EMBEDDER=openai_text_embedding_3_small \
  -e EMBEDDING_DIMENSIONS=1536 \
  airweave-backend-test \
  python -c "
from airweave.domains.embedders.dense.openai import OpenAIDenseEmbedder
import asyncio
e = OpenAIDenseEmbedder(api_key='<azure-key>', model='text-embedding-3-small', dimensions=1536)
result = asyncio.run(e.embed('hello world'))
print(f'vector dim: {len(result.values)}')  # Should print: vector dim: 1536
"
```

## v1.1 plan

When Gooclaim's own `gooclaim-knowledge` pipeline goes live in v1.1
(memory: `project_s5_airweave_strategy.md`), this fork may be deprecated
entirely if we move away from Airweave. Until then, this is the
production path.
