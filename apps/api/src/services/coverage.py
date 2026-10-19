"""报道来源地域与实际观测覆盖；不把总部当作事件发生地。"""

from collections import Counter
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.ingestion.registry import load_registry
from src.models.operations import OperationalState
from src.models.news import News
from src.services.publisher_identity import publisher_id


def source_health_label(value: dict, now: datetime) -> str:
    if not value:
        return "not_checked"
    if not value.get("success"):
        return "failing"
    latest = value.get("latest_published_at")
    if not latest:
        return "no_verified_dates"
    if datetime.fromisoformat(latest) < now - timedelta(hours=72):
        return "stale"
    checked = value.get("last_checked")
    if not checked or datetime.fromisoformat(checked) < now - timedelta(hours=2):
        return "overdue"
    return "healthy"


async def source_coverage(session: AsyncSession, hours: int = 24, admin: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    registry = load_registry(include_disabled=True)
    states = {
        s.key: s.value
        for s in (
            await session.scalars(
                select(OperationalState).where(OperationalState.key.like("source:%"))
            )
        ).all()
    }
    rows = list(
        (
            await session.scalars(
                select(News).where(
                    News.time_quality == "verified",
                    News.published_at >= now - timedelta(hours=hours),
                    News.published_at <= now,
                )
            )
        ).all()
    )
    publishers = set()
    countries = set()
    languages = set()
    regions = Counter()
    categories = Counter()
    for n in rows:
        meta = n.raw_metadata or {}
        publishers.add(publisher_id(n))
        if meta.get("publisher_country") and meta["publisher_country"] != "UN":
            countries.add(meta["publisher_country"])
        if meta.get("publisher_region"):
            regions[meta["publisher_region"]] += 1
        languages.add(n.language)
        categories.update(meta.get("source_categories", []))
    effective_ids = {s.source_id for s in load_registry()}
    sources = []
    for s in registry:
        state = states.get("source:" + s.source_id, {})
        item = {
            "id": s.source_id,
            "publisher": s.name,
            "publisher_id": s.publisher_id,
            "language": s.language,
            "country": s.country,
            "region": s.region,
            "enabled": s.source_id in effective_ids,
            "health": source_health_label(state, now)
            if s.source_id in effective_ids
            else "disabled",
            "last_success": state.get("last_success"),
        }
        if admin:
            item.update(config=s.model_dump(), operation=state)
        sources.append(item)
    return {
        "window_hours": hours,
        "observed_at": now.isoformat(),
        "coverage_basis": "publisher location and reporting language; not incident location or global completeness",
        "configured_feeds": len(sources),
        "enabled_feeds": len(effective_ids),
        "healthy_feeds": sum(s["health"] == "healthy" for s in sources),
        "failing_feeds": sum(s["health"] == "failing" for s in sources),
        "current_articles": len(rows),
        "observed_publishers": len(publishers),
        "publisher_countries": sorted(countries),
        "reporting_languages": sorted(languages),
        "publisher_regions": dict(regions),
        "feed_categories": dict(categories),
        "sources": sources,
    }
