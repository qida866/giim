"""完整证据身份审核后原子合并；旧事件与修订仍可追溯。"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.event import Event, EventNews
from src.models.news import News
from src.models.operations import OperationalState
from src.llm import LLMClient
from src.vector_store import QdrantVectorStore
from src.services.story_matching import fragment_candidates
from src.services.story_review import membership_hash, review_story
from src.services.story_brief import prepare_story_brief
from src.services.event_update import publish_events
from src.services.event_preparation import PreparedEvent
from src.services.event_history import record_revision
from src.services.publisher_identity import publisher_id


async def load_fragments(session: AsyncSession, store: QdrantVectorStore) -> tuple[list[Event], list[list[News]], dict[int, list[float]]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    events = list((await session.scalars(select(Event).where(
        Event.status == 'active', Event.last_updated_at >= cutoff,
        Event.provenance.is_not(None),
    ).order_by(Event.last_updated_at.desc(), Event.id).limit(1600))).all())
    memberships = {e.id: [] for e in events}
    pairs = (await session.execute(select(EventNews.event_id, News).join(
        News, News.id == EventNews.news_id).where(EventNews.event_id.in_(memberships)))).all()
    for eid, news in pairs:
        memberships[eid].append(news)
    events = [e for e in events if memberships[e.id] and len(memberships[e.id]) <= 24
              and all(n.time_quality == 'verified' for n in memberships[e.id])]
    groups = [memberships[e.id] for e in events]
    ids = list({n.id for g in groups for n in g})
    client = await store._get_client()
    points = await client.retrieve(store._collection_name, ids=ids, with_vectors=True) if ids else []
    return events, groups, {p.id: p.vector for p in points}


async def commit_consolidation(
    session: AsyncSession, events: list[Event], members: list[News], item: PreparedEvent
) -> str:
    canonical = min(events, key=lambda e: (e.first_seen_at, str(e.id)))
    expected = membership_hash(members)
    try:
        for member in members:
            await session.refresh(member, with_for_update=True)
        if membership_hash(members) != expected:
            raise ValueError('Evidence changed during consolidation review')
        overlaps = set((await session.scalars(select(EventNews.event_id).join(Event).where(
            Event.status == 'active', EventNews.news_id.in_([n.id for n in members])))).all())
        if overlaps - {e.id for e in events}:
            raise ValueError('Unreviewed active event overlaps consolidation')
        # 在新旧版本之间保留每个来源事件的快照和外键。
        for event in events:
            old = list((await session.scalars(select(News).join(EventNews).where(
                EventNews.event_id == event.id))).all())
            await record_revision(session, event, old, {n.id for n in old})
        prior = [eid for e in events for eid in
                 (e.provenance or {}).get('consolidation', {}).get('source_event_ids', [])]
        source_ids = sorted(set(prior + [str(e.id) for e in events if e.id != canonical.id]))
        item.continuation_of = canonical.id
        item.news = members
        item.provenance['consolidation'] = {'source_event_ids': source_ids,
            'canonical_event_id': str(canonical.id), 'reviewed_at': datetime.now(timezone.utc).isoformat()}
        await publish_events(session, [item], commit=False)
        for event in events:
            if event.id != canonical.id:
                event.status = 'superseded'
                event.provenance = {**(event.provenance or {}), 'canonical_event_id': str(canonical.id)}
        await session.commit()
        return str(canonical.id)
    except Exception:
        await session.rollback()
        raise


async def consolidate_stories(
    session: AsyncSession, store: QdrantVectorStore, llm: LLMClient | None,
    max_calls: int = 6, apply: bool = True,
) -> dict:
    events, groups, vectors = await load_fragments(session, store)
    candidates = fragment_candidates(groups, vectors)
    candidates.sort(key=lambda edge: (
        any((events[k].provenance or {}).get('mode') == 'ai_joint_verified' and len(groups[k]) > 1 for k in edge[:2]),
        len({publisher_id(n) for k in edge[:2] for n in groups[k]}) > 1,
        edge[2]), reverse=True)
    candidates = candidates[:40]
    result = {'candidate_pairs': len(candidates), 'calls_reserved': 0, 'merged': [], 'deferred': 0}
    if not apply:
        result['candidates'] = [{'events': [str(events[i].id), str(events[j].id)],
            'titles': [events[i].title, events[j].title], 'similarity': score}
            for i, j, score in candidates[:50]]
        return result
    if llm is None:
        return result
    state = await session.get(OperationalState, 'story_match_decisions')
    now = datetime.now(timezone.utc)
    cache = {k:v for k,v in (state.value if state else {}).items() if v.get('expires_at','') > now.isoformat()}
    used = set()
    for i, j, score in candidates:
        if i in used or j in used:
            continue
        members = list({n.id:n for n in groups[i] + groups[j]}.values())
        digest = membership_hash(members)
        if digest in cache:
            continue
        if result['calls_reserved'] + 4 > max_calls:
            break
        result['calls_reserved'] += 4
        try:
            review = await review_story(llm, members)
            item = await prepare_story_brief(llm, members, review) if review.accepted else None
        except Exception:
            review, item = None, None
        if item is not None:
            canonical = await commit_consolidation(session, [events[i], events[j]], members, item)
            result['merged'].append({'canonical_event_id': canonical, 'members': len(members),
                                     'relation': review.relation})
            used.update((i,j))
        else:
            result['deferred'] += 1
            cache[digest] = {'outcome': review.relation if review else 'review_failure',
                'expires_at': (now + timedelta(hours=24 if review and not review.accepted else 2)).isoformat()}
    if state:
        state.value = cache
    else:
        session.add(OperationalState(key='story_match_decisions', value=cache))
    await session.commit()
    return result
