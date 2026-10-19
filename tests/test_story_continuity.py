"""跨窗口连续性保持身份且不重复历史修订。"""

import hashlib
import json
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from src.models.event import EventNews
from src.models.event_revision import EventRevision
from src.models.news import News
from src.services.continuity import validate_continuation
from src.services.event_update import publish_events, PreparedEvent
from src.services.story_state import preserve_stories
from tests.test_event_intelligence import article


def test_continuity_requires_exact_anchors_on_both_sides():
    previous = [article(1, hours=4)]
    current = [article(2)]
    raw = {
        "same_bounded_story": True,
        "relation": "update_to_same_incident",
        "reason": "Follow-up",
        "anchors": [{"news_id": 1, "quote": previous[0].title}],
    }
    with pytest.raises(ValueError, match="both evidence sides"):
        validate_continuation(json.dumps(raw), previous, current)
    raw["anchors"].append({"news_id": 2, "quote": current[0].title})
    assert validate_continuation(json.dumps(raw), previous, current).same_bounded_story
    raw["anchors"][1]["quote"] = "invented fact"
    with pytest.raises(ValueError, match="Invalid continuity quote"):
        validate_continuation(json.dumps(raw), previous, current)


@pytest.mark.asyncio
async def test_followup_preserves_identity_membership_and_noop_revision(db_session, sample_events):
    event = sample_events[0]
    old = list(
        (
            await db_session.scalars(
                select(News).join(EventNews).where(EventNews.event_id == event.id)
            )
        ).all()
    )
    for n in old:
        n.published_at -= timedelta(days=4)
    initial = PreparedEvent(
        old, "Initial incident", "Original evidence", {"mode": "source_excerpt"}
    )
    await publish_events(db_session, [initial])
    update = News(
        source_name="Update publisher",
        source_url="https://example.test/update",
        title="Officials update the same incident",
        content="Investigation update.",
        language="en",
        published_at=old[0].published_at + timedelta(days=4),
        time_quality="verified",
        url_hash=hashlib.sha256(b"update-url").hexdigest(),
        content_hash=hashlib.sha256(b"update-body").hexdigest(),
    )
    db_session.add(update)
    await db_session.flush()
    followup = PreparedEvent(
        [update],
        update.title,
        update.content,
        {"mode": "ai_joint_verified", "continuity": {"relation": "update_to_same_incident"}},
        event.id,
    )
    assert await publish_events(db_session, [initial, followup]) == 1
    assert event.news_count == 3
    assert event.event_type == "ongoing"
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(EventRevision)
            .where(EventRevision.event_id == event.id)
        )
        == 2
    )
    remaining, preserved = await preserve_stories(db_session, [event], [update])
    assert remaining == []
    assert len(preserved[0].news) == 3
    await publish_events(db_session, preserved)
    assert event.title == update.title
    assert event.news_count == 3
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(EventRevision)
            .where(EventRevision.event_id == event.id)
        )
        == 2
    )
