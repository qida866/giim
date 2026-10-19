# Public release candidate validation

Validated October 19, 2026 against the Phase 3 implementation imported onto the existing public repository history. No public deployment or push occurred during validation.

- Docker image build: passed with the candidate's dependencies and source.
- Fresh application/test database migrations: passed through `d4e5f6071829`.
- Full suite: **132 passed, one existing structlog warning, 5.76 seconds**.
- Public synthetic recall demonstration: six authored reports; four positive pairs and eleven negative pairs were grouped/separated as labeled, before and after review. Two new identity reviews were performed. This is a tiny execution check, not the historical Phase 3 benchmark or a general quality claim.
- HTTP frontend, health and readiness checks: 200.
- Relative documentation file links and whitespace validation: passed.
- Candidate credential scan: no high-signal provider/private keys or matching local credentials found. Pattern scanning is heuristic and is not a security certification.

Tests used separate containers, ports, application/test databases and vector volumes. Existing model weights were reused read-only; first-time download was not revalidated. Full integration tests and synthetic identity review used the configured provider. The original application's report/event/link/revision/vector counts were unchanged. The test environment was disposable.

The first migration attempt ran before fresh PostgreSQL startup completed and failed with connection refused. The documented startup now uses `docker compose up -d --wait postgres qdrant`; migrations then succeeded. This was a startup-order documentation issue, not a failing test or application regression. No application code was changed to make tests pass.

The test fixture now requires an explicit `TEST_DATABASE_URL` instead of a hardcoded password fallback. It still enforces a database name ending in `_test`; rollback and temporary-vector isolation remain covered.

The candidate preserves existing public Git history. Already-public credential examples and author metadata cannot be erased by a normal additive update. Local reuse of the historical database credential must be rotated; any history cleanup would require separate explicit authorization. Restricted raw evaluation data from unpublished local commits is not included in the incoming history.

No project code license has been added. Synthetic demonstration data does not substitute for redistribution clearance on the original research corpus. See [licensing](licensing.md) and [evaluation](evaluation.md).
