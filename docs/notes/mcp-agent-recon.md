# Task 2 reconnaissance — November 10, 2026

Authoritative specification: complete Task 2 instructions supplied in the user message. Independent branch `feature/mcp-agent`, from public default base `651ffbc1a038c76c7c0d74be30bcc2b4538faf4d`. Task 1 is complete on a separate branch; its commits are not merged. The feature workspace was clean. Main and private research worktrees remain untouched.

Structure: `apps/api/src/`, `scripts/`, `tests/`, `frontend/`, `alembic/`, deployment files, source registry and public evaluation artifacts. Read README, architecture/licensing/deployment docs, actual REST routes, request schemas, models, current LLM client, Docker and tests. Existing OpenAI-compatible LLM client exposes chat(request), metrics and close; it belongs to ingestion/publication and must not be replaced for ADK.

Actual HTTP contracts, also captured from app.openapi():
- GET /api/v1/events/today: hours 1–168, limit 1–50, offset, region and category. No language filter; MCP may post-filter the returned bounded page and must disclose the limitation.
- POST /api/v1/search/events: query 1–500, hours 1–720, top_k 1–50, optional threshold. Read-only despite POST. Returns ranked events and report metadata; event-search deliberately omits similarity score. MCP must not invent it.
- GET /api/v1/events/{event_id}: UUID, offset >=0, limit <=100. Event/articles, current supporting IDs and latest 20 revisions. Revisions/history are not interchangeable with current evidence. Generic dict OpenAPI response means code and controlled runtime fixtures are also required to verify shape.
- GET /api/v1/coverage: hours 1–168, aggregate observed publishers/languages/regions, not universal supported/global coverage. Some requested counts may be unsupported; return null explicitly instead of expanding API scope.
- GET /api/v1/ready: base checks storage but does not check lazy model readiness (Task 1 fixed that separately). Task 2 adapter must report search readiness as unknown unless model-loaded state is exposed, even if HTTP returns 200.
- Admin/ingestion/dependency-detail routes are forbidden to MCP/agent.

Known clean-base packaging defect: public base imports model modules event_revision.py and operations.py that were accidentally ignored during release staging. Record the clean-clone migration/test collection failure, restore the exact existing Phase 3 files and anchor model weight ignores locally, independently of Task 1. This is a minimal prerequisite correction, not a Task 1 merge.

MCP design: independently installed REST-only adapter with explicit method/path allowlist, validated origin/config, bounded response streaming, typed envelopes, source-policy excerpt caps, deterministic UUID/URL associations, transport authentication and stderr-only logging. No DB/Qdrant/internal imports. Five named tools only. Metadata is not automatically claim-bearing evidence; full detail returns only policy-authorized excerpts and current-support membership.

Agent design: independently installed official ADK runtime; per-request in-memory session and transport, Researcher LLM tool rounds (max three) over a constrained MCP gateway (max five details), Coordinator draft plus at most one revision, separate Verifier model/schema, then a deterministic gate based on the immutable gateway ledger. Only exact attributed extractive statements may reach the default final answer; model approval alone cannot authorize novel factual prose. Conflicting current-source quotes remain attributed, with uncertainty. Tool budgets, model-call/token/request deadlines and no general shell/files/web tools are enforced in code. Fake ADK BaseLlm responses traverse the same Runner/agent/MCP/validator path rather than bypassing it.

Dependencies: keep existing API requirements/image independent, since new ADK/MCP versions may require different HTTP/Starlette packages. Verify current official docs and installed SDK source in a separate pinned environment before choosing tested APIs. Public docs currently identify MCP v2 stable and ADK offers an MCP extra; install/test their actual compatibility before pinning a combination.

Licensing: no project license selected; original publisher corpora withheld. Public demo/evaluation uses authored fixtures. Do not fetch live feeds, call a paid model, modify original databases, expose excerpts publicly or add private traces. .runs/ must be ignored; traces redact secrets, exact-match private values and common credential patterns, and separate nullable measured usage from synthetic/fake execution.

No paid calls, cloud resources, merges or pushes are authorized. Baseline and final commands/outcomes will be saved under docs/evidence/mcp-agent/; previous Task 1 test counts are not Task 2 results.
