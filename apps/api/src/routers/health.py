"""健康检查路由模块，提供服务与依赖连通性检查。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.deps import get_db

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """返回 API 基础健康状态。"""
    return {"status": "ok", "version": "0.1.0"}


@router.get("/health/db")
async def health_db(session: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """检查数据库连接状态。"""
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "service": "postgres"}


@router.get("/health/qdrant")
async def health_qdrant(request: Request) -> dict[str, str]:
    """检查 Qdrant 连接状态。"""
    request.app.state.qdrant_client.get_collections()
    return {"status": "ok", "service": "qdrant"}
