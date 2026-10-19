"""固定真实多语言语料评估；仅内存执行，不写 PostgreSQL 或 Qdrant。"""

import argparse
import asyncio
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sys
import time
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from src.embedding import EmbeddingClient, EmbeddingRequest
from src.llm import LLMClient
from src.models.news import News
from src.services.event_quality import build_candidates, generate_event
from src.services.claim_verification import verify_claims, all_supported
from src.services.continuity import assess_continuation


async def evaluate(use_llm: bool) -> dict:
    corpus = json.loads(Path("evaluation/global-events.json").read_text())
    rows = corpus["articles"]
    news = [
        News(
            id=r["id"],
            title=r["title"],
            content=r["content"],
            source_name=r["publisher"],
            source_url=r["url"],
            language=r["language"],
            published_at=datetime.fromisoformat(r["published_at"]),
            time_quality="verified",
        )
        for r in rows
    ]
    by_id = {n.id: n for n in news}
    labels = {r["id"]: r["event_label"] for r in rows}
    started = time.monotonic()
    embedder = EmbeddingClient()
    encoded = []
    for offset in range(0, len(news), 32):
        batch = await embedder.embed(
            EmbeddingRequest(
                texts=[n.title + "\n\n" + n.content[:2000] for n in news[offset : offset + 32]]
            )
        )
        encoded.extend(r.vector for r in batch.results)
    vectors = np.asarray(encoded)
    groups = build_candidates(news, vectors.tolist())
    assignments = {n.id: i for i, group in enumerate(groups) for n in group}
    counts = Counter()
    for i, a in enumerate(news):
        for b in news[i + 1 :]:
            expected = labels[a.id] == labels[b.id]
            actual = assignments[a.id] == assignments[b.id]
            counts[
                "true_pairs"
                if actual and expected
                else "false_merges"
                if actual
                else "missed_pairs"
                if expected
                else "separated_negatives"
            ] += 1
    queries = corpus["retrieval_cases"]
    query_vectors = await embedder.embed(EmbeddingRequest(texts=[q["query"] for q in queries]))
    retrieval = []
    for case, vector in zip(queries, query_vectors.results, strict=True):
        eligible = [i for i, n in enumerate(news) if n.language == case["target_language"]]
        order = sorted(eligible, key=lambda i: float(vectors[i] @ vector.vector), reverse=True)
        ranked = [news[i].id for i in order]
        retrieval.append(
            {
                **case,
                "top_ids": ranked[:5],
                "top1_matches_label": bool(ranked) and labels[ranked[0]] == case["label"],
                "first_relevant_rank": next(
                    (i + 1 for i, nid in enumerate(ranked) if labels[nid] == case["label"]), None
                ),
            }
        )
    result = {
        "articles": len(news),
        "labeled_events": len(set(labels.values())),
        "languages": dict(Counter(n.language for n in news)),
        "candidate_pairs": dict(counts),
        "candidate_groups": [[n.id for n in g] for g in groups],
        "mixed_groups": [[n.id for n in g] for g in groups if len({labels[n.id] for n in g}) > 1],
        "retrieval": retrieval,
        "continuity": [],
        "grounding": [],
        "limitations": corpus["methodology"],
        "embedding_seconds": round(time.monotonic() - started, 2),
    }
    if use_llm:
        llm = LLMClient()
        try:
            for case in corpus["continuity_cases"]:
                try:
                    decision = await assess_continuation(
                        llm,
                        [by_id[i] for i in case["prior_ids"]],
                        [by_id[i] for i in case["new_ids"]],
                    )
                    result["continuity"].append(
                        {
                            **case,
                            "decision": decision.model_dump(),
                            "matches_label": decision.same_bounded_story == case["expected"],
                        }
                    )
                except Exception as exc:
                    result["continuity"].append({**case, "error_type": type(exc).__name__, "error": str(exc)[:500] if isinstance(exc, ValueError) else "provider failure"})
            for name, ids, expected in [
                ("google-fine-multilingual", [792, 1252, 998], True),
                ("korean-english-review", [1577, 1408], True),
                ("different-meetings", [1757, 1790], False),
                ("unrelated-weather", [995, 1518], False),
            ]:
                try:
                    evidence = [by_id[i] for i in ids]
                    draft = await generate_event(llm, evidence)
                    review = await verify_claims(llm, draft, evidence) if draft.coherent else None
                    result["grounding"].append(
                        {
                            "name": name,
                            "matches_coherence_label": draft.coherent == expected,
                            "draft": draft.model_dump(),
                            "review": review.model_dump() if review else None,
                            "all_supported": all_supported(review) if review else None,
                        }
                    )
                except Exception as exc:
                    result["grounding"].append({"name": name, "error_type": type(exc).__name__, "error": str(exc)[:500] if isinstance(exc, ValueError) else "provider failure"})
            result["llm_usage"] = llm.metrics
        finally:
            await llm.close()
    result["duration_seconds"] = round(time.monotonic() - started, 2)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--output", default="/tmp/giim-global-evaluation.json")
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.llm))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in {"candidate_groups", "grounding", "continuity"}
            }
        )
    )
