# GIIM test report

The completed Phase 3 baseline passed 132 tests in development and a standalone image. October 19 release preparation independently passed 132 tests (one existing structlog warning) in a freshly built, isolated Docker environment; its non-integration selection passed 121 tests with 11 deselected. Those runs reused cached model weights and included live provider integrations for the full suite.

Coverage includes transactional consolidation and history, changed-evidence invalidation, primary-action and participant boundaries, publisher identity, official incident-ID deduplication, source reliability, semantic search, claim rejection, authentication, vector reconciliation, advisory locking, rollback and pipeline recovery. No xfail tests were deleted to obtain green results.

The fresh-configuration run initially exposed an ingestion test's hardcoded example token: the application correctly returned 403 for a credential that did not match the generated configuration. The test now explicitly configures a test-only token and uses a bearer header. Application authentication was not weakened. The historical asyncpg event-loop failure did not recur.

The public release also removes the hardcoded fallback database password from test setup: `TEST_DATABASE_URL` is required and must name a separate `_test` database. Use the README migration and test commands. Never point tests at the application database.

Current candidate-specific test outcomes are recorded in `docs/public-release-validation.md`. Synthetic evaluation is separate from regression tests and from the historical real-excerpt diagnostics; see `docs/evaluation.md`. No sustained uptime, load certification or perfect LLM grounding is claimed.
