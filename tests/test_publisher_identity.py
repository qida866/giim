"""历史别名在覆盖与独立性中只算一个发布机构。"""

from sqlalchemy.ext.asyncio import AsyncSession
from src.models.event import Event

import pytest
from src.services.evidence_coverage import evidence_coverage
from src.services.publisher_identity import publisher_id
from src.services.coverage import source_coverage
from tests.test_event_intelligence import article


def test_legacy_and_canonical_bbc_are_one_origin() -> None:
    old, new = article(1), article(2)
    old.source_name = ' BBC News - World '
    old.raw_metadata = {}
    new.raw_metadata = {'publisher_id': 'bbc', 'ownership_group': 'bbc'}
    assert publisher_id(old) == publisher_id(new) == 'bbc'
    result = evidence_coverage([old, new])
    assert result['publishers'] == result['independent_evidence_groups'] == 1
    new.raw_metadata = {'publisher_id': 'another publisher'}
    assert evidence_coverage([old, new])['publishers'] == 2


@pytest.mark.asyncio
async def test_public_coverage_normalizes_legacy_bbc(db_session: AsyncSession, sample_events: list[Event]) -> None:
    from sqlalchemy import select
    from src.models.news import News
    news = list((await db_session.scalars(select(News))).all())
    for index, row in enumerate(news):
        row.source_name = 'BBC News - World'
        row.time_quality = 'verified'
        row.raw_metadata = {'publisher_id': 'bbc'} if index % 2 else {}
    await db_session.flush()
    result = await source_coverage(db_session, 168)
    assert result['observed_publishers'] == 1
