"""合并事务、旧版本保留与证据变化撤回测试。"""

from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select, func
from src.models.event import Event, EventNews
from src.models.event_revision import EventRevision
from src.models.news import News
from src.services.event_preparation import PreparedEvent
from src.services.story_consolidation import commit_consolidation
from src.services.story_state import preserve_stories
from src.services.story_review import membership_hash
from src.services.event_quality import evidence_hash


async def members(session: AsyncSession, events: list[Event]) -> list[News]:
    return list((await session.scalars(select(News).join(EventNews).where(
        EventNews.event_id.in_([e.id for e in events])))).all())


@pytest.mark.asyncio
async def test_consolidation_keeps_ids_links_and_original_history(db_session: AsyncSession, sample_events: list[Event], async_client_db: AsyncClient) -> None:
    events=sample_events[:2];news=await members(db_session,events)
    for n in news:n.time_quality='verified'
    item=PreparedEvent(news,'Current report','Current summary',{'mode':'ai_joint_verified','evidence_ids':[news[-1].id]})
    canonical_id=await commit_consolidation(db_session,events,news,item)
    active=[e for e in events if e.status=='active'];old=[e for e in events if e.status=='superseded']
    assert len(active)==len(old)==1
    assert str(active[0].id)==canonical_id
    assert old[0].provenance['canonical_event_id']==canonical_id
    assert active[0].news_count==4
    assert len(await members(db_session,old))==2
    assert await db_session.scalar(select(func.count()).select_from(EventRevision))==3
    response=(await async_client_db.get('/api/v1/events/'+canonical_id)).json()
    assert len(response['revisions'])==3
    assert response['current_support_ids']==[news[-1].id]


@pytest.mark.asyncio
async def test_consolidation_commit_failure_rolls_back_all_changes(db_session: AsyncSession, sample_events: list[Event], monkeypatch: pytest.MonkeyPatch) -> None:
    events=sample_events[:2];news=await members(db_session,events)
    ids=[e.id for e in events];titles=[e.title for e in events]
    await db_session.commit()
    monkeypatch.setattr(db_session,'commit',AsyncMock(side_effect=RuntimeError('Injected commit failure')))
    item=PreparedEvent(news,'Changed','Changed',{'mode':'ai_joint_verified'})
    with pytest.raises(RuntimeError,match='Injected'):
        await commit_consolidation(db_session,events,news,item)
    saved=[await db_session.get(Event,i) for i in ids]
    assert [e.title for e in saved]==titles
    assert all(e.status=='active' for e in saved)
    assert await db_session.scalar(select(func.count()).select_from(EventRevision))==0
    assert len(await members(db_session,saved))==4


@pytest.mark.asyncio
async def test_changed_article_withdraws_old_claims_without_llm(db_session: AsyncSession, sample_events: list[Event]) -> None:
    event=sample_events[0];news=await members(db_session,[event])
    event.provenance={'continuity':{'relation':'update_to_same_incident'},'membership_hash':membership_hash(news),
                      'evidence_hash':evidence_hash(news),'mode':'ai_joint_verified','citations':[{'text':'Old assertion'}]}
    _,stable=await preserve_stories(db_session,[event],news)
    assert stable[0].summary==event.summary
    news[-1].content='Correction to an important fact in the report.'
    _,changed=await preserve_stories(db_session,[event],news)
    assert changed[0].provenance['revalidation_pending']
    assert changed[0].provenance['citations']==[]
    assert changed[0].provenance['mode']=='source_excerpt'
    assert changed[0].summary!=event.summary


@pytest.mark.asyncio
async def test_negative_decision_cache_makes_repeated_match_noop(db_session: AsyncSession, sample_events: list[Event], monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace
    from src.services import story_consolidation as module
    from src.services.story_review import StoryReview
    events=sample_events[:2]
    groups=[await members(db_session,[e]) for e in events]
    vectors={n.id:[1.0,0.0] for g in groups for n in g}
    monkeypatch.setattr(module,'load_fragments',AsyncMock(return_value=(events,groups,vectors)))
    review=AsyncMock(return_value=StoryReview(relation='ambiguous',identity='',reason='Different actions'))
    monkeypatch.setattr(module,'review_story',review)
    first=await module.consolidate_stories(db_session,SimpleNamespace(),SimpleNamespace(),max_calls=4)
    assert first['deferred']==1
    second=await module.consolidate_stories(db_session,SimpleNamespace(),SimpleNamespace(),max_calls=4)
    assert second['calls_reserved']==0
    assert review.await_count==1


@pytest.mark.asyncio
async def test_consolidation_rejects_unreviewed_overlapping_card(db_session: AsyncSession, sample_events: list[Event]) -> None:
    events = sample_events[:2]
    news = await members(db_session, events)
    db_session.add(EventNews(event_id=sample_events[2].id, news_id=news[0].id, cluster_method='test'))
    await db_session.commit()
    ids = [e.id for e in sample_events]
    item = PreparedEvent(news, 'Changed', 'Changed', {'mode': 'ai_joint_verified'})
    with pytest.raises(ValueError, match='Unreviewed active event'):
        await commit_consolidation(db_session, events, news, item)
    saved = [await db_session.get(Event, eid) for eid in ids]
    assert all(e.status == 'active' for e in saved)
    assert await db_session.scalar(select(func.count()).select_from(EventRevision)) == 0


@pytest.mark.asyncio
async def test_consolidation_preserves_both_lineages_when_evidence_changes(db_session: AsyncSession, sample_events: list[Event]) -> None:
    events = sample_events[:2]
    ancestors = [str(e.id) for e in sample_events[2:4]]
    for event, ancestor in zip(events, ancestors):
        event.provenance = {'consolidation': {'source_event_ids': [ancestor]}}
    news = await members(db_session, events)
    for n in news:
        n.time_quality = 'verified'
    item = PreparedEvent(news, 'Current', 'Current summary', {'mode': 'ai_joint_verified'})
    canonical_id = await commit_consolidation(db_session, events, news, item)
    canonical = next(e for e in events if str(e.id) == canonical_id)
    assert set(ancestors) <= set(canonical.provenance['consolidation']['source_event_ids'])
    news[0].content = 'Material correction'
    _, pending = await preserve_stories(db_session, [canonical], news)
    assert pending[0].provenance['consolidation'] == canonical.provenance['consolidation']
    assert pending[0].provenance['revalidation_pending']


@pytest.mark.asyncio
async def test_failed_revalidation_cools_down_until_evidence_changes(db_session: AsyncSession, sample_events: list[Event], monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace
    from src.services import story_state
    from src.services.event_update import publish_events
    from src.services.story_review import StoryReview
    event = sample_events[0]
    news = await members(db_session, [event])
    event.provenance = {'continuity': {'relation': 'update'}, 'membership_hash': membership_hash(news),
                        'mode': 'ai_joint_verified'}
    news[0].content = 'Corrected evidence requiring revalidation'
    reviewer = AsyncMock(return_value=StoryReview(relation='ambiguous', identity='', reason='Defer'))
    monkeypatch.setattr(story_state, 'review_story', reviewer)
    _, first = await preserve_stories(db_session, [event], news, SimpleNamespace(), 4)
    await publish_events(db_session, first)
    metrics = {}
    _, second = await preserve_stories(db_session, [event], news, SimpleNamespace(), 4, metrics)
    assert second[0].provenance['mode'] == 'source_excerpt'
    assert metrics['revalidation_calls_reserved'] == 0
    assert reviewer.await_count == 1
    news[0].content += ' Another material correction.'
    await preserve_stories(db_session, [event], news, SimpleNamespace(), 4)
    assert reviewer.await_count == 2
