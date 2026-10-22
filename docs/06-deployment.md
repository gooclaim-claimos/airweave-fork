# 06 — Deployment

## Where it runs

Dev only: one AWS EC2 instance runs the Data Sources stack with `docker compose`
(`docker/docker-compose.yml`), next to the LiteLLM gateway it calls. There is no CI
deploy; changes are deployed by hand from the `release/dev` branch.

The Helm charts in `helm/datasources-*` (and their ExternalSecret / ingress templates)
describe an earlier Kubernetes setup. Nothing runs on them today.

The checkout on the instance may differ from the repository: its compose file and
`.env` are the live ones (for example the Temporal namespace). Never copy the repo's
compose file over the live one; apply a compose change by editing the live file.

## The env file rule

Every compose command must pass the env file:

```bash
cd docker
docker compose --env-file ../.env -f docker-compose.yml <command>
```

Why: compose interpolates `${BACKEND_IMAGE:-ghcr.io/airweave-ai/airweave-backend:latest}`,
`${SVIX_JWT_SECRET}` and the other `${...}` values from the env file it is given, or from
`docker/.env` if there is one. `env_file: ../.env` only feeds the containers. Without
`--env-file ../.env`:

- `backend` and `temporal-worker` start on the **upstream** image;
- `SVIX_JWT_SECRET` in the `environment:` block becomes empty and overrides the value from
  `env_file`; `Settings` rejects it and the backend crash-loops.

Check before recreating:

```bash
docker compose --env-file ../.env -f docker-compose.yml config | grep -E 'image:|TEMPORAL_NAMESPACE'
```

## Deploying a backend change

`backend` and `temporal-worker` bind-mount `../backend:/app`, so the image only provides
dependencies; the code is whatever is on disk.

1. Commit and push to `release/dev`.
2. Back up the current backend directory on the instance.
3. Copy the committed files only — `git archive <sha> <paths>` piped to `tar -x` in the
   instance's checkout. Never sync a working tree (it would carry ignored files).
4. Recreate both services:

   ```bash
   cd docker
   docker compose --env-file ../.env -f docker-compose.yml \
     up -d --no-deps --force-recreate backend temporal-worker
   ```

5. The backend runs Alembic on start. Check `/health/ready` and the `alembic_version`
   table (head today: `0004`).

A change to `backend/pyproject.toml` / `poetry.lock` needs a new backend image, not just
a file copy; set it in `BACKEND_IMAGE` in `.env`.

## Deploying a frontend change

The frontend is a built image (`frontend/Dockerfile`, which runs `vite build`, so
`frontend/.env.production` — `VITE_GOOCLAIM_MODE=true` — is baked in).

1. Build the image on the instance from a `git archive` of the commit, tagged with the
   commit.
2. Point `FRONTEND_IMAGE` in `.env` at it (keep a backup of `.env`).
3. Recreate: `docker compose --env-file ../.env -f docker-compose.yml --profile frontend
   up -d --no-deps --force-recreate frontend`.
4. Keep the previous image for rollback.

## Deploying a Vespa schema change

`vespa-init` deploys `vespa/app` when it runs. Adding fields deploys without reindexing;
renaming or retyping fields needs a reindex (a re-sync of every collection). Run
`vespa-init` again after copying the new `vespa/app`.

## Rollback

- Backend: restore the backed-up directory and recreate `backend temporal-worker`.
  A migration that already ran stays applied. All four Gooclaim revisions have a
  downgrade; `0004`'s moves buckets back to the shared folder, which re-opens the
  cross-tenant problem it fixed — do not downgrade past it.
- Frontend: set `FRONTEND_IMAGE` back to the previous tag and recreate.

## After the instance starts

If the backend reports unhealthy at first, Vespa and migrations may still be starting;
wait for `/health/ready`. Check that `temporal-worker` is running: a stopped worker
means no sync runs, and nothing in the backend says so. Long-running services restart
`unless-stopped`.
