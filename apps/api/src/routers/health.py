"""健康检查路由模块，提供服务与依赖连通性检查。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.deps import get_db

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    """返回 API 基础健康状态。"""
    return {"status": "ok", "version": request.app.version}


@router.get("/health/db")
async def health_db(session: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """检查数据库连接状态。"""
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "service": "postgres"}


@router.get("/health/qdrant")
async def health_qdrant(request: Request) -> dict[str, str]:
    """检查 Qdrant 连接状态。"""
    import asyncio

    await asyncio.to_thread(request.app.state.qdrant_client.get_collections)
    return {"status": "ok", "service": "qdrant"}


@router.get("/ready")
async def readiness(request: Request, session: AsyncSession = Depends(get_db)):
    from fastapi.responses import JSONResponse
    from src.models.operations import OperationalState

    try:
        await session.execute(text("SELECT 1"))
        vectors = await request.app.state.vector_store.health()
        state = await session.get(OperationalState, "pipeline")
        value = state.value if state else {}
        return JSONResponse(
            {
                "status": "ready" if vectors else "degraded",
                "database": True,
                "vectors": vectors,
                "pipeline_status": value.get("status", "not_run"),
                "last_update": value.get("finished_at"),
            },
            status_code=200 if vectors else 503,
        )
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)
