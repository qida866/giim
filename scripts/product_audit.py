"""只读产品与覆盖快照；关键词仅生成供人工核验的参考候选。"""

import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import statistics
import sys
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from src.db.session import AsyncSessionLocal, async_engine
from src.models.news import News
from src.models.event import Event, EventNews
from src.models.operations import OperationalState
from src.services.coverage import source_coverage
from src.services.evidence_coverage import evidence_coverage
from src.utils.events import current_score


async def audit() -> dict:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        coverage = await source_coverage(session, 168, admin=True)
        news = list(
            (
                await session.scalars(
                    select(News).where(
                        News.time_quality == "verified",
                        News.published_at >= now - timedelta(days=7),
                        News.published_at <= now,
                    )
                )
            ).all()
        )
        events = list(
            (
                await session.scalars(
                    select(Event).where(
                        Event.status == "active",
                        Event.last_updated_at >= now - timedelta(days=7),
                        Event.last_updated_at <= now,
                        Event.id.in_(
                            select(EventNews.event_id).where(
                                EventNews.news_id.in_([n.id for n in news])
                            )
                        ),
                    )
                )
            ).all()
        )
        links = (
            await session.execute(
                select(EventNews.event_id, EventNews.news_id).where(
                    EventNews.event_id.in_([e.id for e in events])
                )
            )
        ).all()
        ids_by_event = {e.id: set() for e in events}
        events_by_news = {}
        for eid, nid in links:
            ids_by_event[eid].add(nid)
            events_by_news.setdefault(nid, []).append(str(eid))
        by_id = {n.id: n for n in news}
        details = []
        for event in sorted(events, key=lambda e: current_score(e, now), reverse=True):
            members = [by_id[i] for i in ids_by_event[event.id] if i in by_id]
            counts = evidence_coverage(members)
            details.append(
                {
                    "id": str(event.id),
                    "title": event.title,
                    "summary": event.summary,
                    "score": current_score(event, now),
                    "coverage": counts,
                    "category": (event.provenance or {}).get("category"),
                    "mode": (event.provenance or {}).get("mode"),
                    "news_ids": sorted(ids_by_event[event.id]),
                    "continuity": (event.provenance or {}).get("continuity"),
                    "grounding": (event.provenance or {}).get("grounding_review"),
                }
            )
        reference = json.loads(Path("evaluation/coverage-reference.json").read_text())
        candidates = []
        for case in reference["references"]:
            matches = [
                n
                for n in news
                if all(
                    t.casefold() in (n.title + " " + n.content).casefold()
                    for t in case["candidate_terms"]
                )
            ]
            candidates.append(
                {
                    **case,
                    "candidate_reports": [
                        {
                            "id": n.id,
                            "title": n.title,
                            "url": n.source_url,
                            "publisher": n.source_name,
                            "excerpt": n.content[:350],
                            "event_ids": events_by_news.get(n.id, []),
                        }
                        for n in matches
                    ],
                }
            )
        history = await session.get(OperationalState, "pipeline_history")
        publisher_counts = [d["coverage"]["publishers"] for d in details]
        lags = [max(0, (n.fetched_at - n.published_at).total_seconds() / 60) for n in news]
        return {
            "observed_at": now.isoformat(),
            "coverage": coverage,
            "event_counts": {
                "total": len(events),
                "single_publisher": sum(c == 1 for c in publisher_counts),
                "two_plus_publishers": sum(c >= 2 for c in publisher_counts),
                "three_plus_publishers": sum(c >= 3 for c in publisher_counts),
                "mean_publishers": statistics.mean(publisher_counts) if publisher_counts else 0,
                "median_publishers": statistics.median(publisher_counts) if publisher_counts else 0,
                "modes": dict(Counter(d["mode"] for d in details)),
            },
            "ingestion_lag_minutes": {
                "median": statistics.median(lags) if lags else None,
                "note": "Includes initial feed backfill; not steady-state breaking-news latency.",
            },
            "events": details,
            "reference_candidates": candidates,
            "pipeline_history": history.value if history else {},
        }


if __name__ == "__main__":

    async def main() -> None:
        try:
            result = await audit()
            Path("/tmp/giim-product-audit.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            )
            print(json.dumps(result["event_counts"]))
        finally:
            await async_engine.dispose()

    asyncio.run(main())
