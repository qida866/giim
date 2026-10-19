"""重要性、广度和新鲜度的可解释启发式，不把报道量当成真理。"""

from datetime import datetime, timedelta, timezone
import math
from src.models.news import News
from src.services.evidence_coverage import evidence_coverage


def rank_event(
    news: list[News], now: datetime | None = None, importance: dict | None = None
) -> tuple[float, dict, str]:
    now = now or datetime.now(timezone.utc)
    coverage = evidence_coverage(news)
    first = min(n.published_at for n in news)
    last = max(n.published_at for n in news)
    recency = math.exp(-max(0, (now - last).total_seconds() / 3600) / 36)
    origin_score = min(coverage["independent_evidence_groups"] / 4, 1)
    geographic = min(len(coverage["publisher_regions"]) / 4, 1)
    multilingual = min(max(0, len(coverage["languages"]) - 1) / 2, 1)
    volume = min(math.log1p(len(news)) / math.log(11), 1)
    recent = [n for n in news if n.published_at >= now - timedelta(hours=6)]
    velocity = min(evidence_coverage(recent)["independent_evidence_groups"] / 4, 1) if recent else 0
    # 只有经引用及支持性复核的解释才启用模型影响等级。
    level = "unknown"
    if (
        importance
        and importance.get("mode") == "ai_joint_verified"
        and importance.get("why_it_matters")
    ):
        level = importance.get("importance", "unknown")
    impact = {"unknown": 0.15, "minor": 0.1, "substantial": 0.6, "major": 1}.get(level, 0.15)
    score = (
        0.22 * recency
        + 0.35 * impact
        + 0.20 * origin_score
        + 0.10 * geographic
        + 0.05 * multilingual
        + 0.05 * velocity
        + 0.03 * volume
    )
    factors = {
        "formula": "v3",
        "recency": round(recency, 4),
        "recency_weight": 0.22,
        "importance_level": level,
        "impact": impact,
        "distinct_sources": coverage["publishers"],
        "independent_evidence_groups": coverage["independent_evidence_groups"],
        "article_count": len(news),
        "publisher_region_spread": geographic,
        "language_spread": multilingual,
        "reporting_velocity": velocity,
        "volume": round(volume, 4),
        "scored_at": now.isoformat(),
    }
    return (
        round(score, 4),
        factors,
        "ongoing" if (last - first).total_seconds() > 86400 else "incident",
    )
