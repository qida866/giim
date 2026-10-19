> Historical engineering report. Referenced raw evaluation files are retained in the local research archive and are not distributed in this release. See `docs/evaluation.md` for public reproduction limits.

# GIIM Reliability report

## Phase 3 update — September 28–29, 2026 UTC

Phase 3 preserves isolated tests, admin protection, source failure isolation, vector reconciliation and the pipeline advisory lock. Consolidation locks/rechecks evidence and commits one canonical update with both histories atomically; unreviewed overlapping cards are rejected. Material evidence changes invalidate review caches; failed revalidation reuses a safe excerpt for at most two hours while evidence is unchanged. The September 28 backup restored separately with 2,952 news, 2,075 events, 2,490 links and zero orphans, at unchanged schema head d4e5f6071829. Actual repeat-run costs and vector audits are recorded in the Phase 3 report; bounded caches are not an unconditional zero-cost promise. A stable final pass used zero new embeddings and zero LLM calls in 10.19 seconds. Local health/readiness return 200 and unauthenticated admin access returns 403. No sustained uptime or public deployment claim is added.

The record below preserves the dated Phase 2 baseline; its numbers are historical, not current Phase 3 counters.

---

## Repeated operation

Six sequential pipeline runs on September 22 all succeeded:

| Run | Seconds | Quality LLM calls | Continuity calls | Embeddings |
|---|---:|---:|---:|---:|
| 1 | 32.61 | 15 | 0 | 0 |
| 2 | 40.02 | 16 | 1 | 0 |
| 3 | 25.91 | 12 | 0 | 0 |
| 4 | 3.84 | 0 | 0 | 0 |
| 5 | 3.81 | 0 | 0 | 0 |
| 6 | 3.88 | 0 | 0 | 0 |

Mean: **18.34 seconds**. Run two made one supported continuity link. Earlier runs cleared deferred reviews; the last three demonstrate normal-budget no-op behavior after that backlog, not forced zero-budget settings. Separate earlier zero-budget experiments are not used as proof of normal no-op efficiency. Negative-decision cache expiry, new content and changing windows can legitimately trigger later work.

This was a bounded repeated-run soak, not days of unattended uptime or a load test. The local scheduler is not running after validation. On September 23 feeds correctly became overdue and the 24-hour feed empty. Production configuration retains a 30-minute scheduler; registry per-feed polling intervals are hints, not independently enforced adaptive schedules.

## Failure isolation and recovery

Sources use bounded concurrent fetches, retries, response-size/public-address checks, redirect controls, independent transactions and persistent last success/failure. The real 304 redirect-classification defect was fixed and covered through the actual wrapper. The final real refresh succeeded on all 39 feeds in 77.12 seconds, with 111 inserts and four not-modified responses. Source/schema/timestamp failures remain visible instead of being interpreted as no news.

The pipeline uses a PostgreSQL advisory lock and atomic event/revision persistence. Regression tests exercise duplicate suppression, preserved last-good events on failure, vector failure and scheduler recovery after database connection errors. Cached evidence and deferred review bound LLM work. This is not a demonstration that every possible process interruption, network partition or database outage recovers without intervention.

An independent restoration of the pre-Phase-2 backup recovered 821 news, 87 events and 365 links. Clean schema migration succeeded. September 23 vector audit checked 1,262 eligible records: zero missing, stale, metadata-mismatched or orphaned vectors. Historical unversioned vectors (748) are retained intentionally.

## Runtime and cost

Earlier larger review runs took approximately 132–204 seconds, depending on pending generation. The final small benchmark used 11 logical/actual requests, 13,275 prompt tokens and 2,997 completion tokens, completing in 35.02 seconds including 14.83 seconds embedding. These figures are workload observations, not provider billing totals. No dollar-cost estimate is asserted.

CPU bge-m3 requires substantial memory: earlier measured CLI peak was about 2.1 GiB; API search process about 1.9 GiB. Avoid overlapping unnecessary embedding workers on a small host. The default LLM budget and publisher-balanced window limit cost and coverage; deferred items can remain source excerpts.

## Security and deployment

The image runs non-root; development ports remain loopback-bound. Production uses private database services, Caddy, restricted container privileges and secret validation. Administration requires a bearer token; unauthenticated September 23 smoke check returned 403. Public source coverage omits sensitive operational configuration. Existing HTML escaping, safe links, CSP, request-body/rate limits and untrusted-news prompt boundaries are retained.

Registry URLs are operator-controlled, not a public URL submission feature. Address checks reduce SSRF exposure but do not eliminate DNS-rebinding risk. Model instruction separation and support review reduce prompt-injection effects without proving immunity. No full penetration test was performed.

The validated Phase-2 image now runs at localhost:8000 with the actual registry mount; the temporary smoke container was removed. Health responds successfully, though its version literal remains 0.2.0 while application metadata is 0.3.0. Public deployment, TLS issuance and continuous hosted monitoring remain unperformed pending server/domain access. Source redistribution rights must be reviewed before publishing stored local evidence.

## Operational follow-up

Use protected operations and the CLI to inspect last success/failure, source health and vectors. Before public operation, arrange scheduled backups/restore drills, sustained ingestion monitoring, resource/latency measurement under expected traffic and source-rights review. Reduce story fragmentation through measured evaluation; do not hide uncertainty or fabricate additional corroboration to improve apparent product completeness.
