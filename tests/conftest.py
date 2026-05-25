"""测试全局夹具: HTTP 客户端、giim_test 库 savepoint 会话、样例事件。"""

from __future__ import annotations

import hashlib
import os
import sys
import uuid
from collections.abc import AsyncGenerator, Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

_DEFAULT_TEST_DATABASE_URL = (
    "postgresql+asyncpg://giim:giim@postgres:5432/giim_test"
)

os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("DATABASE_URL", _DEFAULT_TEST_DATABASE_URL)
os.environ.setdefault("QDRANT_URL", "http://qdrant:6333")
os.environ.setdefault("QDRANT_API_KEY", "")
os.environ.setdefault("DEEPSEEK_API_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("EMBEDDING_API_KEY", "")
os.environ.setdefault("INGESTION_TRIGGER_TOKEN", "dev-trigger-token-change-me")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.db.deps import get_db  # noqa: E402
from src.main import app  # noqa: E402
from src.models.event import Event, EventNews  # noqa: E402
from src.models.news import News  # noqa: E402

OverrideGetDb = Callable[[], AsyncGenerator[AsyncSession, None]]


def override_get_db(session: AsyncSession) -> OverrideGetDb:
    """为 FastAPI 生成 get_db 覆盖, 使路由复用测试中的 savepoint 会话。"""

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    return _override


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """测试库连接串 (可由环境变量 DATABASE_URL 覆盖)。"""
    return os.environ["DATABASE_URL"]


@pytest_asyncio.fixture(scope="session")
async def test_engine(test_database_url: str) -> AsyncGenerator[AsyncEngine, None]:
    """会话级测试引擎, 指向 giim_test。"""
    engine = create_async_engine(test_database_url, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """函数级会话: 外层事务 + savepoint, 用例结束整体回滚。"""
    async with test_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest_asyncio.fixture
async def sample_events(db_session: AsyncSession) -> list[Event]:
    """预填 5 条已评分事件及关联新闻 (用于 events router 测试)。"""
    now = datetime.now(timezone.utc)
    scores = (0.91, 0.75, 0.55, 0.35, 0.15)
    events: list[Event] = []

    for idx, score in enumerate(scores, start=1):
        event = Event(
            id=uuid.uuid4(),
            title=f"GIIM 测试事件 {idx}",
            summary=f"测试摘要 {idx}",
            status="active",
            first_seen_at=now,
            last_updated_at=now,
            news_count=2,
            impact_score=score,
            event_type="breaking" if idx == 1 else "ongoing",
            impact_factors={
                "source_count": 0.9,
                "authority": 0.8,
                "recency": 0.7,
                "duration": 1.0,
            },
        )
        db_session.add(event)
        events.append(event)

    await db_session.flush()

    for idx, event in enumerate(events, start=1):
        for sub in (1, 2):
            slug = f"evt{idx}-n{sub}-{uuid.uuid4().hex[:8]}"
            url = f"http://test.giim.local/{slug}"
            content = f"正文 {slug}"
            news = News(
                source_name=f"测试源{idx}",
                source_url=url,
                title=f"新闻标题 {slug}",
                content=content,
                language="zh",
                published_at=now,
                url_hash=_sha256_hex(url),
                content_hash=_sha256_hex(content),
            )
            db_session.add(news)
            await db_session.flush()
            db_session.add(
                EventNews(
                    event_id=event.id,
                    news_id=news.id,
                    cluster_method="test",
                ),
            )

    await db_session.flush()
    return events


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """无 DB 覆盖的 HTTP 客户端 (health / ingestion 等)。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def async_client_db(
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """覆盖 get_db 的 HTTP 客户端, 与 db_session 共用 savepoint 事务。"""
    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
