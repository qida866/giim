"""事件检索、来源导航与敏感相似度隔离。"""

from sqlalchemy.ext.asyncio import AsyncSession
import pytest

from unittest.mock import AsyncMock
from sqlalchemy import select
from src.models.event import Event, EventNews
from src.routers.search import SearchAPIResponse, SearchHit
from src.routers.event_search import event_search, SearchAPIRequest


async def test_event_search_groups_reports_without_presenting_similarity(
    db_session, sample_events, monkeypatch
):
    event = sample_events[0]
    nid = await db_session.scalar(select(EventNews.news_id).where(EventNews.event_id == event.id))
    result = SearchAPIResponse(
        query="incident",
        results=[
            SearchHit(
                news_id=nid,
                title="Source reporting",
                url="https://example.test/report",
                source="Publisher",
                published_at=event.last_updated_at.isoformat(),
                score=0.9,
                event_ids=[str(event.id)],
                language="en",
            )
        ],
        total=1,
        duration_ms=1,
    )
    monkeypatch.setattr("src.routers.event_search.semantic_search", AsyncMock(return_value=result))
    response = await event_search(SearchAPIRequest(query="incident"), db_session, None, None)
    assert response["total_events"] == 1
    assert response["events"][0]["id"] == str(event.id)
    assert response["total_reports"] == 1
    assert "score" not in response["reports"][0]


async def test_region_and_category_navigation(async_client_db, db_session, sample_events):
    sample_events[0].provenance = {
        "coverage": {"publisher_regions": ["Africa"]},
        "category": "health",
    }
    await db_session.flush()
    result = await async_client_db.get("/api/v1/events/today?region=Africa&category=health")
    assert result.status_code == 200
    assert [e["id"] for e in result.json()["events"]] == [str(sample_events[0].id)]
    assert (await async_client_db.get("/api/v1/events/today?category=technology")).json()[
        "events"
    ] == []


async def test_search_relevance_precedes_ai_summary_availability(db_session: AsyncSession, sample_events: list[Event], monkeypatch: pytest.MonkeyPatch) -> None:
    strongest, weaker = sample_events[:2]
    strongest.provenance = {'mode': 'source_excerpt'}
    weaker.provenance = {'mode': 'ai_joint_verified'}
    hits = []
    for event, score in [(strongest, .95), (weaker, .45)]:
        nid = await db_session.scalar(select(EventNews.news_id).where(EventNews.event_id == event.id))
        hits.append(SearchHit(news_id=nid, title=event.title, url='https://example.test/report',
            source='Publisher', published_at=event.last_updated_at.isoformat(), score=score,
            event_ids=[str(event.id)], language='en'))
    result = SearchAPIResponse(query='Japan typhoon', results=hits, total=2, duration_ms=1)
    monkeypatch.setattr('src.routers.event_search.semantic_search', AsyncMock(return_value=result))
    response = await event_search(SearchAPIRequest(query='Japan typhoon'), db_session, None, None)
    assert [e['id'] for e in response['events']] == [str(strongest.id), str(weaker.id)]
