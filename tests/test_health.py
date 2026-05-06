"""健康检查接口测试模块。"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(async_client: AsyncClient) -> None:
    """验证健康检查接口返回状态正常。"""
    response = await async_client.get("/api/v1/health")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
