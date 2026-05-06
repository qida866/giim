"""新闻路由模块，提供新闻分页查询接口。"""

from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.deps import get_db
from src.models.news import News
from src.schemas.news import NewsListResponse, NewsResponse

router = APIRouter()


@router.get("/news", response_model=NewsListResponse)
async def list_news(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    language: str | None = Query(default=None),
    source: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> NewsListResponse:
    """按条件分页查询新闻列表。"""
    conditions = []
    if language:
        conditions.append(News.language == language)
    if source:
        conditions.append(News.source_name == source)

    total_stmt = select(func.count()).select_from(News)
    items_stmt = select(News)
    if conditions:
        total_stmt = total_stmt.where(*conditions)
        items_stmt = items_stmt.where(*conditions)

    total = int(await session.scalar(total_stmt) or 0)
    offset = (page - 1) * page_size
    items_stmt = items_stmt.order_by(News.published_at.desc()).offset(offset).limit(page_size)
    rows = await session.scalars(items_stmt)
    items = [NewsResponse.model_validate(row) for row in rows.all()]
    total_pages = ceil(total / page_size) if total > 0 else 0

    return NewsListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
