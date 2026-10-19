# Phase 3 event recall: public engineering report

Historical measurements recorded September 28–29, 2026 UTC. This public report retains aggregate findings and methodological limitations; publisher excerpts, raw model responses, source-level operational snapshots and the full local development narrative are not distributed.

## Problem and implementation

The Phase 2 candidate gates fragmented related reports while occasionally merging actions that merely shared actors. Phase 3 retained bge-m3 and the initial HDBSCAN thresholds, then added bounded story-fragment retrieval, full-member LLM identity review, a separate primary-action audit, participant matching, transactional consolidation, evidence-driven cache invalidation and revised current-support selection. API/frontend presentation distinguishes current supporting evidence from story history.

## Results

| 90-report diagnostic | Phase 2 | Phase 3 |
|---|---:|---:|
| True-positive pairs | 95 | 115 |
| False-negative pairs | 51 | 31 |
| False-positive pairs | 4 | 0 |
| True-negative pairs | 3,855 | 3,859 |

The net gain includes 40 recovered positives and 20 newly split positives. It is not improvement on every case.

The expanded corpus contains 223 reports and 74 explicit relationships: 33 positive, 21 negative and 20 ambiguous. Final review joined 28 positives, separated all 21 scored negatives and joined five ambiguous cases. These counts are also available in [machine-readable aggregates](evaluation/phase3-summary.json).

## Evidence quality and acceptance limits

Labels were agent-proposed and separately model-reviewed, not independently human-adjudicated. The former holdout informed iteration. The corpus is English-skewed and purposive. Exact quotation checks and model agreement do not establish truth or independence.

Live review still found broad contextual reporting entering a developing-story continuation. Full acceptance was therefore qualified: recall improved, but the action-versus-context boundary is unfinished. Zero false merges on the explicit scored negatives does not imply zero real errors. A fresh human-adjudicated continuation benchmark is the next quality gate.

## Operational observations

The historical suite passed 132 tests, including a standalone image run. One recorded warm stable pipeline pass used zero new embeddings and zero LLM requests in 10.19 seconds. New evidence, expired caches and rule changes legitimately require additional work; this is not a throughput or uptime guarantee. No public deployment, sustained load result or universal global coverage claim is made.

All application functionality remains in the public release. Original detailed research artifacts are preserved locally. The authored public demo exercises the pipeline but cannot reproduce the withheld corpus's measurements. See [evaluation instructions](docs/evaluation.md), [architecture](docs/architecture.md), and [test report](FINAL_TEST_REPORT.md).
