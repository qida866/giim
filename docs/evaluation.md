# Evaluation methodology and public reproducibility

There are three distinct validation layers:

1. Regression tests exercise safety, API behavior, persistence, matching boundaries and integrations. The Phase 3 baseline and release preparation passed 132 tests. Live integrations need bge-m3, Qdrant and a configured provider; see the README for isolated database setup.
2. The **public synthetic demonstration** contains six fictional reports across three events in English, Chinese and Spanish. Run `scripts/evaluate_recall.py --corpus evaluation/synthetic-demo.json --budget 20 --output /tmp/synthetic-recall.json` inside a fresh configured evaluation container. It exercises the actual embedding/candidate/review path without writing business or vector tables. LLM calls may cost money and vary. It does not measure general multilingual quality or reproduce historical scores.
3. The **historical research diagnostics** used 90 real excerpts and an expanded 223-report corpus. Only aggregate measurements are distributed in `evaluation/phase3-summary.json`; source excerpts and raw quoted model outputs are withheld pending redistribution clearance. No replacement fixture is presented as the basis of those results.

## Historical findings: September 28–29, 2026 UTC

The original set contains 146 positive and 3,859 negative report pairs. Phase 2 produced 95 true-positive pairs, 51 false negatives, four false-positive pairs and 3,855 true negatives. Phase 3 produced 115, 31, zero and 3,859 respectively. Forty positive pairs were recovered and twenty were newly split. Pair totals do not describe a representative global distribution.

The expanded set has 74 explicit relationship cases: 33 agreed positive, 21 topic-only and 20 ambiguous. Final review joined 28 positive cases and five ambiguous cases, separating all 21 scored negatives. Labels were proposed by the development agent and checked in a separate blinded model pass. They are not independently human-adjudicated. Initially held-out cases informed later iterations, so they are now diagnostic cases, not an untouched test set.

A contextual continuation over-merge remained in the live audit. The zero scored false-merge count must not be read as perfect real-world precision. Small retrieval and grounding cases demonstrate capabilities, not universal coverage, factual accuracy or unbiased framing.

## Research-only runners

The original runners remain available to avoid removing functionality:

- `evaluate_global.py` requires the original `evaluation/global-events.json`, including its specific case IDs.
- `evaluate_quality.py` includes authored synthetic examples but also requires the original `evaluation/issue38.json` for its historical comparison.
- `review_phase3_labels.py` expects a separately provided `/tmp/phase3-corpus.json`.
- `evaluate_recall.py --corpus PATH` accepts the documented article schema used by the public demo and original corpora.

Obtain appropriate rights before supplying historical publisher data. Keep it outside the public Git tree. These research prerequisites are intentionally not bundled; running their historical default commands without them will fail. The public command above is the supported distributable demonstration.

The legacy recall runner reads fixed `/tmp/phase3-evaluation-pool.json` and `/tmp/phase3-identity-cache.json` files if present. Use a fresh disposable container per independent corpus to avoid stale cross-corpus vectors or decisions; do not run concurrent corpora in the same container. This cache isolation is existing technical debt, not a newly validated benchmark feature.
