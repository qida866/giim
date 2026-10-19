"""先准备证据输出，再原子发布增量事件；保留旧事件及外键。"""

from __future__ import annotations
import uuid
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.event import Event, EventNews
from src.models.news import News
from src.services.ranking import rank_event
from src.core.logging import get_logger

from src.services.event_preparation import PreparedEvent, prepare_events as prepare_events
from src.services.event_history import record_revision
from src.services.evidence_coverage import evidence_coverage
from src.services.event_quality import evidence_hash
from src.services.story_review import membership_hash

logger = get_logger(__name__)


async def publish_events(session: AsyncSession, prepared: list[PreparedEvent], commit: bool = True) -> int:
    if not prepared:
        return 0
    existing = list((await session.scalars(select(Event).where(Event.status == "active"))).all())
    links = (await session.execute(select(EventNews.event_id, EventNews.news_id))).all()
    memberships = {e.id: set() for e in existing}
    for eid, nid in links:
        if eid in memberships:
            memberships[eid].add(nid)
    targets = {p.continuation_of for p in prepared if p.continuation_of}
    covered = set().union(*(memberships.get(eid, set()) for eid in targets))
    updated_targets = {
        p.continuation_of
        for p in prepared
        if p.continuation_of
        and not {n.id for n in p.news} <= memberships.get(p.continuation_of, set())
    }
    retained = []
    for item in prepared:
        ids = {n.id for n in item.news}
        if item.continuation_of in updated_targets and ids <= memberships.get(
            item.continuation_of, set()
        ):
            continue
        if not item.continuation_of and ids & covered:
            if not ids <= covered:
                raise ValueError("Continuity overlaps an unreviewed mixed candidate")
            continue
        retained.append(item)
    prepared = retained
    used = set()
    incoming = set()
    try:
        for item in prepared:
            ids = {n.id for n in item.news}
            incoming.update(ids)
            # 保留已有 ID；只按实际证据重叠匹配，避免用模糊标题拼接历史事件。
            matches = [
                e
                for e in existing
                if e.id not in used
                and memberships[e.id] & ids
                and (
                    memberships[e.id] <= ids
                    or len(memberships[e.id] & ids) / len(memberships[e.id] | ids) >= 0.5
                )
            ]
            event = (
                max(matches, key=lambda e: len(memberships[e.id] & ids))
                if matches
                else Event(id=uuid.uuid4())
            )
            if item.continuation_of:
                target = next((e for e in existing if e.id == item.continuation_of), None)
                if target is not None and target.id not in used:
                    event = target
                    previous = list(
                        (
                            await session.scalars(
                                select(News).join(EventNews).where(EventNews.event_id == target.id)
                            )
                        ).all()
                    )
                    item.news = list({n.id: n for n in previous + item.news}.values())
                    ids = {n.id for n in item.news}
                    incoming.update(ids)
            prior_ids = memberships.get(event.id, set())
            used.add(event.id)
            score, factors, kind = rank_event(item.news, importance=item.provenance)
            event.title = item.title
            event.summary = item.summary
            event.provenance = {
                **item.provenance,
                "coverage": evidence_coverage(item.news),
                "evidence_hash": item.provenance.get("evidence_hash") or evidence_hash(item.news),
                "membership_hash": membership_hash(item.news),
            }
            event.tags = [item.provenance.get("category", "general")]
            event.first_seen_at = min(n.published_at for n in item.news)
            event.last_updated_at = max(n.published_at for n in item.news)
            event.news_count = len(ids)
            event.status = "active"
            event.impact_score = score
            event.impact_factors = factors
            event.event_type = "ongoing" if item.continuation_of else kind
            session.add(event)
            await session.flush()
            await record_revision(session, event, item.news, prior_ids)
            await session.execute(delete(EventNews).where(EventNews.event_id == event.id))
            session.add_all(
                [
                    EventNews(event_id=event.id, news_id=nid, cluster_method="hdbscan+coherence-v1")
                    for nid in ids
                ]
            )
        for event in existing:
            if event.id not in used and memberships[event.id] & incoming:
                event.status = "superseded"
        if commit:
            await session.commit()
        return len(prepared)
    except Exception:
        await session.rollback()
        raise
