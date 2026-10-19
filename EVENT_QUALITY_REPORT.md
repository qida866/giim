> Historical engineering report. Referenced raw evaluation files are retained in the local research archive and are not distributed in this release. See `docs/evaluation.md` for public reproduction limits.

# GIIM Event quality report

## Phase 3 update — September 28–29, 2026 UTC

Final Phase 3 frozen pair counts: 115 correctly grouped positives, 31 missed positives, zero false merges and 3,859 correctly separated negatives, versus Phase 2's 95/51/4/3,855. This recovers 40 pairs while newly separating 20 previously grouped positives. Trials with broader false joins are retained rather than hidden. The expanded corpus is diagnostic after iterative use, not an untouched holdout; no population accuracy claim is justified. Current evidence and historical coverage are separated, and unsupported revalidation withdraws AI claims. See the Phase 3 report for final expanded/continuity metrics and remaining failures.

Acceptance remains qualified: broader context can still enter developing-story membership, including the Madrid/Barcelona housing example. The original small diagnostic’s zero scored false merges is not proof of error-free live consolidation.

The record below preserves the dated Phase 2 baseline; its numbers are historical, not current Phase 3 counters.

---

## Method and corpus

`evaluation/global-events.json` contains **90 real RSS excerpts across 28 assistant-labeled bounded stories**. Language distribution: en 68, de 2, ru 5, es 3, ar 3, ja 2, fr 2, zh 1, ko 2, pt 2. The sample intentionally probes translations, similar-topic negatives, continuing developments and singleton reporting. Labels were not independently adjudicated; this is diagnostic evaluation, not general accuracy measurement. Evaluation rows were not inserted into live tables.

## Clustering and identity

The preserved bge-m3/HDBSCAN path applies pairwise coherence and a maximum 72-hour candidate span, then reviews at most eight publisher-diverse reports. It does not relax coherence merely to increase publisher counts.

Measured candidate-pair counts: **95 correctly grouped positive pairs, 51 missed same-story pairs, four false merged pairs and 3,855 correctly separated negative pairs**. One mixed group joined press-access litigation and boycott/response reporting (IDs 1800, 1052, 1005, 875, 1469), exposing the boundary between a bounded developing story and a related response. Candidate grouping is measured before downstream generation rejection; the result must not be represented as final published-brief accuracy.

Live UI inspection confirms under-merging: separate typhoon and election cards can describe overlapping developments. Broad topic matches remain insufficient to merge incidents. The original Issue 38 corpus was re-evaluated: separate and joint generation each matched the three coherence labels, six outcomes total. This small comparison does not prove universal superiority of joint prompting.

## Continuity and timelines

Five labeled continuity cases matched expected decisions: FAA outage/resumption and same-storm updates linked; separate Zelensky meetings, unrelated Japan/Brazil weather and a broad G7 response versus one Riyadh incident stayed separate. Production continuity requires a close centroid, bounded chronology, an explicit same-story judgment and quotations from both old and new evidence.

Live story `100a9b58-d6fb-4dce-84bf-30729004c0f2` retained identity for Xi Washington-visit reporting across three revisions (one → three → six reports), including German, English and Russian. Revision history records observations and prior summaries. Publication timelines retain article timestamps; they are not a fully reconstructed incident chronology. Older membership is not evidence that every source confirms the latest claim.

## Retrieval

Eight cross-language queries ranked a label-relevant result first, covering Chinese/Japanese/Korean/Arabic queries and English, German, French, Russian and Portuguese targets. Some target-language pools contain only two records, so 8/8 is a narrow demonstration rather than an estimated multilingual search accuracy. Browser search for Chinese typhoon terms also returned English and multilingual event results. Event search presents reviewed briefs before fallback reporting within its matched result set.

## Grounding and perspectives

All four generation cases matched coherence labels. The Korean-English Uber review brief passed complete claim-support verification. The Google-fine brief passed title and three main claims but failed its significance claim: the reviewer judged wording mixing an eight-year delay and six-year inquiry only partially supported. Distinct legitimate intervals may explain that wording; the gate may over-reject. The recorded result is **blocked**, not a successful grounded brief.

Exact-quote validation and a separate model entailment pass cover retained summary claims, title, significance and optional comparisons. Unsupported or incomplete review falls back to source reporting. Common facts require evidence from distinct estimated reporting origins; single-publisher editions are not treated as independent consensus. Differences and uncertainties are omitted when unsupported. Tests cover fabricated quotations, incomplete review, unrelated support and malicious news text as data. No independent human study of perspective usefulness or factual entailment accuracy has been performed.

## Deduplication and remaining risk

Same-publisher URL/content/title fuzzy-hash rules retain cross-publisher evidence. Same-URL revisions preserve original publication time and recent text history. Ownership, explicit wire attribution and sufficiently long identical text reduce estimated independence; this is incomplete syndication detection. Cross-language headline similarity does not delete legitimate independent reports. Recurring short headlines and sparse excerpts remain ambiguous.

Priority is reducing fragmentation without increasing false merges. Add independently reviewed near-neighbor and continuity negatives, measure both missed links and incorrect joins, then consider candidate/continuity changes. Also review revalidation of cached continuing stories when an existing member article changes, and the presentation of old versus current claims. Rankings and model-support decisions must remain explicitly heuristic.
