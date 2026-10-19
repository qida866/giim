"""事件响应展示与动态分数。"""

from datetime import datetime, timezone
from src.models.event import Event
from src.schemas.events import EventResponse
from src.utils.display import duration_str, event_type_label, stars_for_score


def current_score(event: Event, now: datetime) -> float:
    import math

    f = event.impact_factors or {}
    score = float(event.impact_score or 0)
    if f.get("formula") in {"v2", "v3"}:
        weight = 0.22 if f.get("formula") == "v3" else 0.5
        score = (
            score
            - weight * float(f.get("recency", 0))
            + weight * math.exp(-max(0, (now - event.last_updated_at).total_seconds() / 3600) / 36)
        )
    return round(score, 4)


def _event_to_response(
    rank: int,
    event: Event,
    sources_count: int,
    source_names: list[str] | None = None,
    languages: list[str] | None = None,
) -> EventResponse:
    score = current_score(event, datetime.now(timezone.utc))
    return EventResponse(
        id=event.id,
        rank=rank,
        title=event.title,
        summary=event.summary or None,
        impact_score=score,
        impact_factors=event.impact_factors,
        event_type=event.event_type,
        stars=stars_for_score(score),
        event_type_label=event_type_label(event.event_type),
        first_seen_at=event.first_seen_at,
        last_updated_at=event.last_updated_at,
        duration_str=duration_str(event.first_seen_at, event.last_updated_at),
        news_count=event.news_count,
        sources_count=sources_count,
        source_names=source_names or [],
        languages=languages or [],
        summary_kind=(event.provenance or {}).get("mode", "legacy_ai"),
        generated_at=(event.provenance or {}).get("generated_at"),
        coverage=(event.provenance or {}).get("coverage", {}),
        category=(event.provenance or {}).get("category", "general"),
        why_it_matters=(event.provenance or {}).get("why_it_matters"),
    )
