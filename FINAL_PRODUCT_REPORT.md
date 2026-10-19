> Historical engineering report. Referenced raw evaluation files are retained in the local research archive and are not distributed in this release. See `docs/evaluation.md` for public reproduction limits.

# GIIM Local acceptance report

## Phase 3 update — September 28–29, 2026 UTC

Phase 3 now adds bounded semantic story retrieval, full-member identity review, a headline-only primary-action check, atomic card consolidation, current-support IDs and source-change revalidation. Existing architecture, bge-m3, grounding and source-only fallback remain. Event search now keeps relevance ahead of AI-summary availability. See [the Phase 3 report](PHASE3_EVENT_RECALL_REPORT.md) for final measurements, deferred cases and local release status. Public deployment is still blocked by unavailable server/domain setup.

Acceptance remains qualified: broader context can still enter developing-story membership, including the Madrid/Barcelona housing example. The original small diagnostic’s zero scored false merges is not proof of error-free live consolidation.

The record below preserves the dated Phase 2 baseline; its numbers are historical, not current Phase 3 counters.

---

Prepared September 23, 2026. Implementation: `bd5eac0` and `276f180`, built on the accepted `b8c222d` baseline. This is a local acceptance candidate, not a claim of complete worldwide discovery or public production deployment.

## Delivered product

The existing FastAPI, asynchronous SQLAlchemy/PostgreSQL, Qdrant, bge-m3 and single-host Docker architecture is preserved. Plain JavaScript serves the responsive frontend. DeepSeek-compatible generation adds bounded event intelligence; the model is not a source of news.

A reviewed JSON registry now drives RSS/Atom and official USGS GeoJSON discovery. Independent source transactions, bounded fetches, conditional HTTP, retries and persistent health isolate failures. Publication-time provenance and publisher-preserving deduplication remain intact. Same-URL updates retain the original publication time and recent source revisions.

The pipeline reconciles vectors, selects a publisher-balanced recent window, applies time-bounded HDBSCAN candidate safeguards, reviews coherent evidence, generates title and summary together, validates exact quotations and performs a second claim-support review. Unsupported output falls back to attributed source reporting. Atomic publication and a PostgreSQL advisory lock preserve the prior state on failure and prevent duplicate scheduler execution.

Events expose actual article, publisher, language and publisher-region counts, estimated independent reporting origins, coverage states, cited summaries, supported significance, optional common facts/differences/uncertainties, original reporting and revision history. Conservative continuity can retain event identity across updates. Reporting timelines use source publication times; revision timestamps describe system observations, not invented incident times.

Ranking is a documented heuristic: recency .22, grounded impact .35, reporting origins .20, regions .10, languages .05, velocity .05 and volume .03. It is neither an objective importance score nor a factual-confidence score. Event-first multilingual search and origin/category filters are available; raw article search is preserved.

## Measured acceptance evidence

- Full regression and production-image suite: **90 passed**, one logging warning.
- September 22 real refresh: **39/39 feeds succeeded**, 111 new reports, four HTTP 304 responses.
- September 23 seven-day audit: **1,204 reports, 26 publisher organizations (27 raw identifiers), 10 languages, 18 publisher country/jurisdiction codes**.
- Current stored items: **1,064**, including **91 AI-reviewed summaries and 973 source excerpts**; 58 have at least two publishers and 17 have at least three.
- Six repeated pipeline runs succeeded; final three took 3.84/3.81/3.88 seconds with zero embedding and LLM calls.
- Clean migration, image test, historical backup restore and current vector reconciliation passed. Desktop, mobile, search, filters, source citations and story revisions were inspected.

## Acceptance limitations

The local scheduler is not left running. On September 23 the 39 enabled feeds correctly show overdue, and the 24-hour view is empty because the last validation ingestion was September 22. Select **3 days** or **7 days** to inspect the validated baseline. The production configuration includes a recurring scheduler, but it has not been deployed for continuous service.

Conservative grouping still fragments some stories into multiple cards, including typhoon and election coverage. Many source excerpts remain unreviewed or lack a specific category/importance assessment. The support reviewer can reject valid wording; quotes and model judgments do not prove real-world truth. Perspectives are conditional evidence comparisons, not a comprehensive assessment of disagreement. Publisher headquarters do not identify event location. The health endpoint still carries the legacy `0.2.0` response literal while application metadata is `0.3.0`; this cosmetic version drift is recorded rather than treated as release identity evidence.

Public deployment needs user-owned server/domain access and a source-rights review. Production mode enables 35 feeds: CNA and three Guardian feeds are excluded by their recorded usage restrictions. Existing local evidence would also need review before migration to a public service.

## Local acceptance walkthrough

Open http://localhost:8000/ and select 3 days. Open a multi-publisher event; inspect its claims, source quotations and publisher counts. Open the Xi Washington-visit story and inspect its three observed revisions and multilingual reporting. Try Chinese search for Japanese typhoon reporting, then a publisher-origin and category filter. Compare related typhoon cards to observe the remaining fragmentation directly.

## Recommended next task

Reduce duplicate developing-story cards using a larger, independently reviewed continuity evaluation before changing thresholds. Likely files: `event_quality`, `event_preparation`, `story_state`, `continuity`, their tests and `evaluation/global-events.json`. Risks include merging separate incidents, changing event identity and presenting older reports as confirmation of new claims. Preserve conservative rejection and compare false merges as well as missed links. The current local delivery is ready for acceptance review; broader product quality remains iterative.
