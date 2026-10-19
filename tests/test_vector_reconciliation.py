"""等量但 ID 错配必须被发现。"""

import pytest
from tests.test_vector_store import isolated_vector_store, random_unit_vector
from src.vector_store import VectorPoint, UpsertRequest
from src.services.vector_sync import audit_vectors
from src.models.news import News
from sqlalchemy import select


@pytest.mark.integration
@pytest.mark.asyncio
async def test_equal_counts_do_not_hide_missing_and_orphan(
    db_session, sample_events, isolated_vector_store
):
    store = isolated_vector_store
    await store.ensure_collection()
    news = list((await db_session.scalars(select(News))).all())
    points = [VectorPoint(id=n.id, vector=random_unit_vector(1024), payload={}) for n in news[1:]]
    points.append(VectorPoint(id=999999999, vector=random_unit_vector(1024), payload={}))
    await store.upsert(UpsertRequest(points=points))
    report, pending = await audit_vectors(db_session, store)
    assert report["missing"] == [news[0].id]
    assert report["orphans"] == ["999999999"]
    assert len(report["stale"]) == len(news) - 1
    await store.close()
