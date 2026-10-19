# GIIM stabilization design

An event is one occurrence or a bounded developing story, not a weekly subject bucket. Article evidence remains attributable. bge-m3, PostgreSQL, Qdrant, FastAPI, the CLI and the vanilla frontend remain.

Sequence: isolated async tests → backup and safe persistence → explicit timestamp/dedup provenance → vector reconciliation → conservative event coherence and shared evidence generation → fresh ranking/detail/search → scheduled pipeline → interface/security/build/evaluation.

## Decisions

- Tests override application DATABASE_URL before imports using a validated TEST_DATABASE_URL ending in `_test`; function-scoped async engines retain savepoint isolation.
- Preserve historical rows. Add provenance columns with conservative legacy defaults; new RSS records with unknown dates are retained but excluded from the current feed. Never rewrite unknown dates to now.
- Ingestion suppresses same-source identical reports within a bounded 48-hour window, using a PostgreSQL transaction advisory lock per source. URL uniqueness remains global. Cross-source text copies remain independent evidence.
- HDBSCAN remains a candidate discovery algorithm; current event publishing additionally requires temporal/semantic coherence and a conservative structured evidence check. Insufficiently coherent candidates are rejected; single-source stories must be labeled honestly.
- Evaluate separate generation with shared evidence versus joint structured generation. Prefer joint generation for fewer calls, with explicit article citations and schema validation; it does not validate cluster coherence by itself. On generation failure preserve old published output or an explicitly labeled source-title fallback.
- Publish each accepted event transactionally using stable evidence-overlap identity; never clear the event tables during routine updates. Legacy CLI reclustering must also be atomic and refuse zero output.
- Serve the static frontend from the API on the same origin. One scheduler process runs a serialized pipeline; no broker or new frontend framework.
- Production requires backups, persistent volumes, HTTPS proxy, private DB/vector services, secret-based admin access, bounded requests, and measured model memory. External account provisioning is an independent final blocker.

## Evaluation limits

A small labeled regression corpus detects known failures; it does not establish universal event quality, neutrality or retrieval precision. LLM grounding checks reduce but cannot eliminate errors. Persist source IDs, input hashes, model and generation mode for review.
