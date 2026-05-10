"""采集触发接口测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from src.ingestion.orchestrator_schema import IngestionRunStats

pytestmark = pytest.mark.asyncio


async def test_trigger_ingestion_forbidden_invalid_token(async_client: AsyncClient) -> None:
    """错误 token 返回 403,且 message 为 Invalid token。"""
    response = await async_client.post("/api/v1/ingestion/trigger?token=wrong-token")
    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid token"}


async def test_trigger_ingestion_success_mocked(async_client: AsyncClient) -> None:
    """合法 token 下调 orchestrator,此处 mock 避免真实拉 RSS。"""
    now = datetime.now(timezone.utc)
    fake_stats = IngestionRunStats(
        started_at=now,
        finished_at=now,
        total_duration_ms=1.0,
        sources_total=2,
        sources_succeeded=2,
        sources_failed=0,
        items_fetched_total=10,
        items_inserted_total=5,
        items_skipped_total=3,
        items_failed_total=0,
        per_source=[],
    )
    with patch("src.routers.ingestion.run_ingestion", AsyncMock(return_value=fake_stats)):
        response = await async_client.post(
            "/api/v1/ingestion/trigger?token=dev-trigger-token-change-me"
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["sources_total"] == 2
    assert payload["items_inserted_total"] == 5
