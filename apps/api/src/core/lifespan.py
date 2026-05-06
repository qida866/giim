"""生命周期模块，负责应用启动与关闭资源管理。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from qdrant_client import QdrantClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """管理 FastAPI 应用生命周期。"""
    db_engine: AsyncEngine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )
    qdrant_client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)

    async with db_engine.connect() as connection:
        await connection.execute(text("SELECT 1"))

    app.state.db_engine = db_engine
    app.state.qdrant_client = qdrant_client
    logger.info("应用启动完成", app_env=settings.app_env)

    try:
        yield
    finally:
        await db_engine.dispose()
        qdrant_client.close()
        logger.info("应用关闭完成")
