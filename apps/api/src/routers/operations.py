"""公开聚合覆盖及经鉴权的详细运行状态。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.admin import require_admin
from src.db.deps import get_db
from src.models.operations import OperationalState
from src.services.coverage import source_coverage

router=APIRouter()


@router.get('/coverage')
async def coverage(hours: int = Query(24,ge=1,le=168),session: AsyncSession=Depends(get_db)) -> dict:
    return await source_coverage(session,hours)


@router.get('/admin/operations',dependencies=[Depends(require_admin)])
async def operations(session: AsyncSession=Depends(get_db)) -> dict:
    pipeline=await session.get(OperationalState,'pipeline')
    history=await session.get(OperationalState,'pipeline_history')
    return {'coverage':await source_coverage(session,168,admin=True),'pipeline':pipeline.value if pipeline else None,'pipeline_history':history.value if history else None}
