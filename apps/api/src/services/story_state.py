"""连续故事保留身份；证据改变时撤回旧摘要并重新审核。"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.event import Event, EventNews
from src.models.news import News
from src.llm import LLMClient
from src.services.event_preparation import PreparedEvent
from src.services.event_quality import evidence_hash, select_evidence
from src.services.story_review import membership_hash, review_story
from src.services.story_brief import prepare_story_brief


async def preserve_stories(
    session: AsyncSession, existing: list[Event], news: list[News],
    llm: LLMClient | None = None, max_calls: int = 0, metrics: dict | None = None,
) -> tuple[list[News], list[PreparedEvent]]:
    current_ids = {n.id for n in news}
    preserved: list[PreparedEvent] = []
    excluded: set[int] = set()
    calls = 0
    for event in existing:
        provenance = event.provenance or {}
        if not (provenance.get('continuity') or provenance.get('consolidation')):
            continue
        members = list((await session.scalars(
            select(News).join(EventNews).where(EventNews.event_id == event.id)
        )).all())
        ids = {n.id for n in members}
        if not ids & current_ids:
            continue
        unchanged = provenance.get('membership_hash') == membership_hash(members)
        if not provenance.get('membership_hash'):
            unchanged = provenance.get('evidence_hash') == evidence_hash(members)
        item = None
        attempted = False
        retry_pending = provenance.get('revalidation_retry_after', '') > datetime.now(timezone.utc).isoformat()
        if unchanged and (not provenance.get('revalidation_pending') or retry_pending):
            item = PreparedEvent(members, event.title, event.summary, dict(provenance), event.id)
        elif llm is not None and calls + 4 <= max_calls and len(members) <= 24:
            calls += 4
            attempted = True
            try:
                review = await review_story(llm, members)
                item = await prepare_story_brief(llm, members, review)
                if item:
                    item.continuation_of = event.id
                    for key in ('continuity', 'consolidation'):
                        if provenance.get(key):
                            item.provenance[key] = provenance[key]
            except Exception:
                item = None
        if item is None:
            latest = select_evidence(members, limit=1)[0]
            item = PreparedEvent(members, latest.title, latest.content[:500] or latest.title,
                {'mode': 'source_excerpt', 'citations': [], 'importance': 'unknown', 'category': 'general',
                 'evidence_ids': [latest.id], 'current_support_ids': [latest.id],
                 'revalidation_pending': True, 'continuity': {'relation': 'evidence_changed_pending_review'},
                 'evidence_hash': evidence_hash([latest])}, event.id)
            if attempted:
                item.provenance['revalidation_retry_after'] = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
            if provenance.get('consolidation'):
                item.provenance['consolidation'] = provenance['consolidation']
        excluded.update(ids)
        preserved.append(item)
    if metrics is not None:
        metrics['revalidation_calls_reserved'] = calls
    return [n for n in news if n.id not in excluded], preserved
