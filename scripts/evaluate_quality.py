"""小型固定语料评估；合成案例只在内存中，不写入新闻库。"""

from __future__ import annotations

import argparse
import asyncio
import json
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from src.embedding import EmbeddingClient, EmbeddingRequest
from src.llm import LLMClient
from src.models.news import News
from src.services.event_quality import build_candidates, generate_event


def synthetic_corpus() -> list[News]:
    """显式虚构实体、固定事件标签，避免把真实新闻当成标准答案。"""
    items = [
        (
            "Luma Observatory launches Aurora telescope",
            "Luma Observatory launched the Aurora telescope on Monday to study distant galaxies.",
            "en",
        ),
        ("露玛天文台发射极光望远镜", "露玛天文台周一发射了极光望远镜，用于研究遥远星系。", "zh"),
        (
            "El observatorio Luma lanza el telescopio Aurora",
            "El observatorio Luma lanzó el telescopio Aurora el lunes para estudiar galaxias lejanas.",
            "es",
        ),
        (
            "Flood closes Maren bridge",
            "Flooding closed the Maren bridge on Monday. Local buses were diverted.",
            "en",
        ),
        ("洪水导致马伦大桥关闭", "洪水导致马伦大桥周一关闭，当地公交车改道。", "zh"),
        (
            "Riverton council approves library",
            "The Riverton council approved construction of a public library on Monday.",
            "en",
        ),
    ]
    return [
        News(
            id=10000 + i,
            title=t,
            content=c,
            source_name=f"Synthetic publisher {i}",
            language=l,
            published_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
            source_url=f"https://example.invalid/evaluation/{i}",
            time_quality="synthetic",
        )
        for i, (t, c, l) in enumerate(items)
    ]


async def evaluate(use_llm: bool) -> dict:
    """评估检索、已知混簇和两种同证据生成策略。"""
    import numpy as np

    synthetic = synthetic_corpus()
    real = [
        News(**{**r, "published_at": datetime.fromisoformat(r["published_at"])})
        for r in json.loads(Path("evaluation/issue38.json").read_text())
    ]
    embedder = EmbeddingClient()
    started = time.monotonic()
    all_news = synthetic + real
    encoded = await embedder.embed(
        EmbeddingRequest(texts=[n.title + "\n" + n.content[:2000] for n in all_news])
    )
    vectors = [r.vector for r in encoded.results]
    queries = [
        "极光望远镜发射",
        "Maren bridge flood",
        "biblioteca aprobada por el consejo de Riverton",
    ]
    expected = [{10000, 10001, 10002}, {10003, 10004}, {10005}]
    query_vectors = await embedder.embed(EmbeddingRequest(texts=queries))
    retrieval = []
    for q, vector, relevant in zip(queries, query_vectors.results, expected, strict=True):
        scores = np.asarray(vectors[:6]) @ np.asarray(vector.vector)
        order = np.argsort(-scores)
        retrieval.append(
            {
                "query": q,
                "top_id": synthetic[int(order[0])].id,
                "top1_relevant": synthetic[int(order[0])].id in relevant,
                "ranked_ids": [synthetic[int(i)].id for i in order],
            }
        )
    result = {
        "corpus": "6 explicitly synthetic articles / 3 labeled events; 7 real historical Issue 38 reports",
        "retrieval": retrieval,
        "synthetic_groups": [[n.id for n in g] for g in build_candidates(synthetic, vectors[:6])],
        "issue38_groups": [[n.id for n in g] for g in build_candidates(real, vectors[6:])],
        "embedding_elapsed_seconds": round(time.monotonic() - started, 2),
        "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "generation": [],
        "limitations": "Small diagnostic corpus, not population accuracy; exact quote checks do not prove entailment or neutral framing.",
    }
    if use_llm:
        llm = LLMClient()
        try:
            for name, group, expected_coherent in [
                ("synthetic_same_event", synthetic[:3], True),
                ("synthetic_mixed", [synthetic[0], synthetic[3], synthetic[5]], False),
                ("real_issue38", real, False),
            ]:
                for mode in ("separate", "joint"):
                    started = time.monotonic()
                    try:
                        draft = await generate_event(llm, group, mode)
                        result["generation"].append(
                            {
                                "case": name,
                                "mode": mode,
                                "expected_coherent": expected_coherent,
                                "matches_label": draft.coherent == expected_coherent,
                                "valid_exact_quotes": True,
                                "seconds": round(time.monotonic() - started, 2),
                                "draft": draft.model_dump(),
                            }
                        )
                    except Exception as exc:
                        result["generation"].append(
                            {
                                "case": name,
                                "mode": mode,
                                "error_type": type(exc).__name__,
                                "matches_label": False,
                            }
                        )
        finally:
            await llm.close()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--output", default="/tmp/giim-evaluation.json")
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.llm))
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, ensure_ascii=False))
