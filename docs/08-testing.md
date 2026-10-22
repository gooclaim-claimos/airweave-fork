# 08 — Testing

## Two test trees

| Tree | Contents | Collected by plain `pytest`? |
|---|---|---|
| `backend/tests/` | `unit/` (65 files), `integration/`, `e2e/` | yes (`pytest.ini` `testpaths = tests`) |
| `backend/airweave/**/tests/` | colocated domain and adapter tests (216 files) | **no** |

Run both:

```bash
cd backend
poetry install
poetry run pytest -q tests/unit airweave -n 4
```

`tests/unit` alone misses the domain tests. That has already let a schema change ship
with 15 failing domain tests. `backend/conftest.py` sets every environment variable
`Settings` needs (with `setdefault`), so no `.env` is required and real env vars are not
overridden.

`tests/integration` needs Postgres and other services; `tests/e2e` needs a running stack
(see `backend/tests/README.md`).

### Pre-existing failures

Before calling a failure pre-existing, run the same command on a `git worktree` of the
base commit and compare the failing test names. Only failures present there are
pre-existing.

## Lint

```bash
cd backend
poetry run ruff check .
poetry run ruff format --check .
```

`.pre-commit-config.yaml` (upstream) also runs mypy, import-linter, a unit-test hook and
ESLint.

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

## Gooclaim tests

| Area | Tests |
|---|---|
| Gateway tenant header and labels | `tests/unit/core/test_gateway_tenant.py`, `tests/unit/search/test_openai_provider_names_tenant_*.py`, `airweave/adapters/llm/tests/test_anthropic.py`, `airweave/domains/embedders/dense/tests/test_openai.py`, `airweave/domains/ocr/tests/test_mistral_ocr_gateway.py` |
| Relevance gate | `airweave/adapters/reranker/tests/test_relevance_gate.py`, `airweave/core/container/tests/test_relevance_gate_wiring.py`, `airweave/domains/search/tests/test_browse_only_exclusion.py` |
| Auth order, provisioning, master key | `airweave/api/tests/test_context_resolver*.py`, `airweave/api/tests/test_context.py`, `tests/integration/api/test_role_gating.py` |
| Tenant scoping of entities | `tests/unit/api/test_entity_content_scope.py`, `tests/unit/api/test_entity_original.py` |
| Native Upload | `tests/unit/platform/sources/test_gooclaim_upload.py`, `tests/unit/platform/sources/test_upload_bucket_migration.py` |
| AWS S3 source | `tests/unit/platform/sources/test_s3.py` |
| Library audience | `tests/unit/schemas/test_collection_audience.py`, collection domain tests |
| Pages | `airweave/domains/ocr/tests/test_pages.py`, `airweave/domains/search/adapters/vector_db/tests/test_vespa_client_pages.py` |
| Vespa field rename | `tests/unit/platform/destinations/vespa/` |

The gateway tests use real SDK clients with `httpx.MockTransport` and assert on what
leaves for the wire (headers, model alias, OCR request shape), not on mocks of the
clients.

## CI

There is no server CI for `release/dev`. `.github/workflows/gooclaim-ci.yml` (ruff +
`pytest tests/unit` on Python 3.13) only triggers on `develop`, which is no longer used.
The other workflows in `.github/workflows/` are upstream's. Run the commands above
locally before every push.
