"""Ingestion 触发接口路由。

提供 HTTP 端点用于触发新闻采集,适用于:
- 开发期手动测试
- 未来定时任务(cron 或 GitHub Actions)
- Day 5+ Agent 调用
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Query, Request, Header, status

from src.core.config import settings
from src.core.logging import get_logger
from src.ingestion.orchestrator import run_ingestion
from src.ingestion.orchestrator_schema import IngestionRunStats

logger = get_logger(__name__)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post(
    "/trigger",
    response_model=IngestionRunStats,
    summary="触发一次新闻采集",
    description=(
        "同步执行 RSS 采集 + 去重 + 入库,返回完整统计。"
        "使用 Authorization: Bearer token；仅开发环境兼容 query token。"
    ),
)
async def trigger_ingestion(
    request: Request,
    token: str | None = Query(None, deprecated=True),
    authorization: str | None = Header(None),
) -> IngestionRunStats:
    client_host = request.client.host if request.client else None
    logger.info("采集触发开始", client_ip=client_host)

    expected = settings.ingestion_trigger_token
    supplied = authorization.removeprefix("Bearer ") if authorization else (token if settings.app_env != "production" else None)
    if not expected or not supplied or not secrets.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        logger.warning("采集触发 token 无效", client_ip=client_host)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")

    stats = await run_ingestion()
    logger.info(
        "采集触发结束",
        client_ip=client_host,
        sources_succeeded=stats.sources_succeeded,
        sources_total=stats.sources_total,
        items_inserted_total=stats.items_inserted_total,
        items_fetched_total=stats.items_fetched_total,
        total_duration_ms=round(stats.total_duration_ms, 1),
    )
    return stats
