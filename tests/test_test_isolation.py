"""测试数据库选择与应用 commit 隔离的回归验证。"""
import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import safe_test_url
from src.models.event import Event

@pytest.mark.parametrize('url', [
    'postgresql+asyncpg://x:x@postgres/giim',
    'postgresql+asyncpg://x:x@postgres/postgres',
    'sqlite:///giim_test',
])
def test_unsafe_database_rejected(url: str) -> None:
    with pytest.raises(ValueError):
        safe_test_url(url)

@pytest.mark.asyncio
async def test_application_commit_is_rolled_back(test_engine) -> None:
    event_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(bind=connection, join_transaction_mode='create_savepoint') as session:
            session.add(Event(id=event_id, title='rollback sentinel', first_seen_at=now, last_updated_at=now))
            await session.commit()
            assert await session.scalar(select(Event.id).where(Event.id == event_id)) == event_id
        await transaction.rollback()
    async with AsyncSession(test_engine) as observer:
        assert await observer.scalar(select(Event.id).where(Event.id == event_id)) is None
