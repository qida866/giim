# Deployment and operations

## Decision and measured sizing

Use one Linux VM running production Docker Compose: PostgreSQL, Qdrant, API, a scheduled pipeline process, and Caddy. This is a modest-traffic, single-host deployment, not HA. The actual CPU bge-m3 evaluation process peaked at **2088.2 MiB RSS** on Linux ARM64 while encoding 13 reports and three queries. API and scheduler may each retain a model; provision **8 GB minimum for a small demo**, preferably **16 GB for headroom**, 4 vCPU and at least 40 GB disk. This sizing is an inference from the measured process, not a load-test guarantee. Watch memory during larger/longer batches and resize before increasing concurrency. Embedding calls within a process are serialized.

A standard VM (for example a supported Hetzner Cloud server) keeps both persistent stores and the model cache together with low operational overhead. [Hetzner server documentation](https://docs.hetzner.com/cloud/servers/overview/). Fly remains possible, but its local volumes and replication/recovery planning add complexity here; no historical free-tier or low-memory deployment assumption is retained. [Fly volume documentation](https://fly.io/docs/volumes/overview/). Managed PostgreSQL/vector services reduce host maintenance but add cost and network dependencies. No current price quote or billing commitment was made.

## Remaining user-owned step

Provision a VM/account with billing authorized and a domain you control, then point its A/AAAA records to the VM. No cloud account, target hostname, authorized billing or server access was supplied for this deployment. Everything below is ready to run; no public deployment or certificate issuance has been claimed.

## Install and start

Install Docker Engine and Compose on the chosen host using the vendor's supported instructions. Permit inbound SSH from your own administration address and public 80/443 only. Copy/clone this repository to a directory owned by your deployment user. Do not copy development `.env` secrets into Git.

```sh
cp deploy/production.env.example .env.production
chmod 600 .env.production
openssl rand -hex 32   # generate POSTGRES_PASSWORD
openssl rand -hex 32   # separately generate INGESTION_TRIGGER_TOKEN
# Edit .env.production: domain, password in both DB fields, admin token, optional LLM key.
docker compose -f compose.production.yml config --quiet
docker compose -f compose.production.yml build
# Explicit migration on every release, including when the prior one-shot container already exited.
docker compose -f compose.production.yml run --rm migrate
docker compose -f compose.production.yml up -d
```

Open `https://YOUR_GIIM_DOMAIN`. Caddy provisions and renews certificates when DNS resolves to the host and ports 80/443 are reachable. [Caddy requirements](https://caddyserver.com/docs/automatic-https). Certificate storage is persistent. The API has no host port in this configuration; PostgreSQL/Qdrant are also private to the Docker network. The API trusts proxy headers only because its ingress is restricted to this internal network. Do not expose its container port directly with that trust setting.

The model downloads to the `model_cache` named volume on first use; this can take minutes. Pipeline runs on startup and then 1800 seconds after completion; PostgreSQL locking prevents concurrent pipeline jobs. With no valid AI credentials, single-source excerpts are published and visibly labeled. Administrative ingestion is separate from full pipeline execution and requires a Bearer token; query tokens are disabled in production.

## Validation and monitoring

```sh
docker compose -f compose.production.yml ps
docker compose -f compose.production.yml logs --tail=100 pipeline
curl -fsS https://YOUR_GIIM_DOMAIN/api/v1/ready
docker compose -f compose.production.yml exec api python -m scripts.reconcile_vectors
docker stats --no-stream
```

Check both `pipeline_status` and `last_update`: readiness's database/vector checks do not imply fresh news. Alert when a pipeline is failed or more than two hours stale, eligible sources unexpectedly fall to zero, or disk usage exceeds your operational threshold. Inspect per-source statistics in pipeline logs / `operational_states`. API/scheduler container logs rotate. Arrange host monitoring and off-host backups; these services have not been connected to an external monitoring account.

Limits are per process: 12 search requests/minute/client, 240 other requests/minute/client, 32 KiB bodies, one API worker. Rate limits reset on restart and are not distributed protection. Do not increase API worker count casually: every worker can load another model. A high-traffic rollout needs capacity testing and stronger edge controls.

## Backup and restore

Stop the pipeline while making a coordinated backup. Protect backups as operational data and transfer them to storage outside this VM. PostgreSQL is authoritative for article/event data; Qdrant snapshots additionally preserve historical vectors that are deliberately not re-embedded automatically.

```sh
mkdir -p backups
chmod 700 backups
docker compose -f compose.production.yml stop pipeline
docker compose -f compose.production.yml exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/giim.dump
# Snapshot/download the collection with the internal Qdrant API.
docker compose -f compose.production.yml exec -T api python -c 'import httpx,sys; u="http://qdrant:6333/collections/news_embeddings/snapshots"; r=httpx.post(u,timeout=120); r.raise_for_status(); name=r.json()["result"]["name"]; r=httpx.get(u+"/"+name,timeout=120); r.raise_for_status(); sys.stdout.buffer.write(r.content)' > backups/qdrant.snapshot
docker compose -f compose.production.yml start pipeline
```

Only run the snapshot step once the collection exists. Keep timestamped backup copies rather than overwrite your last good copy. Qdrant snapshot behavior: [official snapshot documentation](https://qdrant.tech/documentation/tutorials-operations/create-snapshot/).

Restore PostgreSQL **into a new, empty database first**, for example `giim_restore_test` (the original local backup was successfully restored this way, producing 748 news / 25 events / 301 links):

```sh
docker compose -f compose.production.yml exec postgres createdb -U giim giim_restore_test
docker compose -f compose.production.yml exec -T postgres pg_restore -U giim -d giim_restore_test --no-owner < backups/giim.dump
# Point a temporary DATABASE_URL at the restored DB and run alembic upgrade head.
```

Validate records and schema before a deliberate DATABASE_URL cutover with API/pipeline stopped. Never restore over the live DB as an unattended step. Qdrant snapshot restoration should likewise target a separate collection first, then set `QDRANT_COLLECTION_NAME` after validation; full disaster-recovery cutover has not been rehearsed remotely. Retain the previous DB/collection for rollback. `docker compose down` preserves named volumes; **do not use `down -v` for a deployed system**.

## Release and rollback

Back up first, build/tag the new image, explicitly run migrations, restart API/pipeline, check readiness and perform search/detail smoke tests. Pin the prior image tag/digest for rollback. Schema rollback is a separate decision: restoring the prior image alone does not undo data migrations. The timestamp migration preserves records and changes HN provenance only. No existing database or vector collection was deleted during completion.

Validated locally: version-locked non-root build, fresh-DB migrations and tests from the image without source mounts, Caddy syntax, Compose validation, loopback-only development bindings and PostgreSQL backup restore. Not validated: real domain DNS, public TLS issuance, provider VM provisioning, long-duration operation or production traffic load.
