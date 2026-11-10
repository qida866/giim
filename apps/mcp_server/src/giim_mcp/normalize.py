"""从实际 API 契约提取允许的字段；不传播任意 provenance。"""

from uuid import UUID

from .config import Settings, safe_url
from .models import Coverage, Detail, EventCard, Readiness, Revision, Source


def card(row: dict) -> EventCard:
    keys = ("id", "title", "summary", "first_seen", "last_updated", "sources_count", "languages")
    values = {k: row[k] for k in keys if k in row}
    # 当前事件搜索不提供分数；不从 rank 或 impact_score 推断相似度。
    values["evidence_status"] = row.get("summary_kind")
    return EventCard(**values)


def source(
    row: dict, event_id: UUID, settings: Settings, support: list[str] | None = None
) -> Source:
    publisher = row.get("source")
    cap = min(settings.excerpt_limit, settings.publisher_caps.get(publisher, 0))
    excerpt = row.get("excerpt")
    return Source(
        article_id=row.get("id", row.get("news_id")),
        event_id=event_id,
        publisher=publisher,
        url=safe_url(row.get("url")),
        published_at=row.get("published_at"),
        language=row.get("language"),
        title=(row.get("title") or "")[:500] or None,
        excerpt=excerpt[:cap] if cap and isinstance(excerpt, str) else None,
        current_support=str(row.get("id")) in support if support is not None else None,
        excerpt_policy="explicit_publisher_cap" if cap else "withheld",
    )


def detail(row: dict, requested: UUID, settings: Settings) -> Detail:
    event = card(row["event"])
    # 归档事件可能指向新 canonical ID；要求调用方重新请求，避免混合事件引用。
    if event.id != requested:
        raise ValueError("Event identity mismatch")
    support = row.get("current_support_ids")
    if support is not None:
        support = [str(UUID(str(value))) for value in support]
    revisions = [
        Revision(
            recorded_at=r.get("recorded_at"),
            origin_event_id=r.get("origin_event_id"),
            title=(r.get("title") or "")[:500] or None,
            evidence_ids=r.get("evidence_ids") or [],
        )
        for r in row.get("revisions", [])[:20]
    ]
    return Detail(
        event=event,
        status=row.get("status"),
        articles=[source(a, event.id, settings, support) for a in row["articles"]],
        total_articles=row.get("total_articles"),
        evidence_ids=support,
        llm_review_status=None,
        revisions=revisions,
    )


def coverage(row: dict) -> Coverage:
    return Coverage(
        observed_at=row.get("observed_at"),
        window_hours=row.get("window_hours", 24),
        observed_languages=row["reporting_languages"],
        observed_publishers=row.get("observed_publishers"),
        current_articles=row.get("current_articles"),
        by_region=row.get("publisher_regions", {}),
        unsupported=[
            "supported_languages",
            "indexed_articles",
            "tracked_events",
            "by_language",
            "by_publisher",
        ],
        basis=row["coverage_basis"],
    )


def readiness(row: dict) -> Readiness:
    status = row["status"]
    def boolean(name: str) -> bool | None:
        return row.get(name) if isinstance(row.get(name), bool) else None
    db, vectors, model = (boolean(k) for k in ("database", "vectors", "model_loaded"))
    ready = (
        False
        if status != "ready" or False in (db, vectors, model)
        else (True if (db, vectors, model) == (True, True, True) else None)
    )
    return Readiness(
        api_status=status,
        database=db,
        vectors=vectors,
        model_loaded=model,
        search_ready=ready,
        note="Storage health alone does not prove search readiness.",
    )
