"""已知混簇、引用、时效和增量发布回归。"""

import json
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from src.models.event import Event, EventNews
from src.models.news import News
from src.services.event_quality import validate_draft, build_candidates, select_evidence
from src.services.event_update import publish_events, PreparedEvent
from src.services.ranking import rank_event


def article(i, title="One specific event happened", source="A", hours=0):
    return News(
        id=i,
        title=title,
        content="The original source reports specific facts.",
        source_name=source,
        language="en",
        published_at=datetime.now(timezone.utc) - timedelta(hours=hours),
        source_url=f"https://example.test/{i}",
    )


def test_complete_link_does_not_chain_unrelated_incidents():
    articles = [article(1), article(2), article(3)]
    groups = build_candidates(articles, [[1, 0], [0.85, 0.527], [0.45, 0.893]])
    assert max(map(len, groups)) < 3


def test_time_boundary_prevents_distant_merge():
    assert len(build_candidates([article(1), article(2, hours=100)], [[1, 0], [1, 0]])) == 2


def test_citation_must_quote_actual_selected_article():
    raw = {
        "coherent": True,
        "reason": "same",
        "title": "One event reported",
        "sentences": [
            {
                "text": "Something factual happened",
                "citations": [{"news_id": 1, "quote": "invented supporting text"}],
            }
        ],
    }
    with pytest.raises(ValueError):
        validate_draft(json.dumps(raw), [article(1)])
    raw["sentences"][0]["citations"][0]["quote"] = "One specific event happened"
    assert validate_draft(json.dumps(raw), [article(1)]).coherent


def test_distinct_sources_outweigh_repeated_articles():
    repeated = [article(i) for i in range(10)]
    diverse = [article(i, source=str(i)) for i in range(4)]
    assert rank_event(diverse)[0] > rank_event(repeated)[0]


def test_evidence_includes_publishers_before_duplicates():
    selected = select_evidence([article(1), article(2), article(3, source="B")], 2)
    assert {n.source_name for n in selected} == {"A", "B"}


@pytest.mark.asyncio
async def test_today_excludes_stale_and_legacy(async_client_db, db_session, sample_events):
    sample_events[0].last_updated_at = datetime.now(timezone.utc) - timedelta(days=10)
    await db_session.flush()
    r = await async_client_db.get("/api/v1/events/today")
    assert len(r.json()["events"]) == 4
    assert r.json()["window_hours"] == 24
    assert (await async_client_db.get("/api/v1/events/today?hours=999")).status_code == 422


@pytest.mark.asyncio
async def test_event_detail_has_attributable_sources(async_client_db, sample_events):
    r = await async_client_db.get("/api/v1/events/" + str(sample_events[0].id))
    assert r.status_code == 200
    assert len(r.json()["articles"]) == 2
    assert r.json()["perspectives"]["mode"] == "attributed_reporting"


@pytest.mark.asyncio
async def test_publish_keeps_stable_id_and_noop(db_session, sample_events):
    event = sample_events[0]
    eid = event.id
    news = list(
        (
            await db_session.scalars(select(News).join(EventNews).where(EventNews.event_id == eid))
        ).all()
    )
    prepared = [PreparedEvent(news, "Updated event", "Sourced summary", {"mode": "source_excerpt"})]
    await publish_events(db_session, prepared)
    assert (await db_session.get(Event, eid)).title == "Updated event"
    assert await publish_events(db_session, []) == 0
    assert await db_session.get(Event, eid) is not None
