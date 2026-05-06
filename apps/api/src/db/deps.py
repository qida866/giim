"""数据库依赖模块，向路由层导出会话依赖。"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db as _get_db


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """导出数据库依赖注入函数。"""
    async for session in _get_db():
        yield session
