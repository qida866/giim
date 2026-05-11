"""LLM 客户端集成与基础行为测试。"""

from __future__ import annotations

import pytest

from src.llm import LLMClient, LLMRequest


@pytest.mark.asyncio
@pytest.mark.integration
async def test_chat_basic() -> None:
    """验证单轮对话可返回有效内容与 token 用量。"""
    client = LLMClient()
    request = LLMRequest(
        messages=[
            {
                "role": "user",
                "content": "请用一句话介绍 GIIM 是什么。",
            }
        ],
        max_tokens=120,
        temperature=0.2,
    )

    response = await client.chat(request)

    assert response.content.strip() != ""
    assert response.usage.total_tokens > 0
    assert response.usage.prompt_tokens > 0


@pytest.mark.asyncio
async def test_chat_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """缺失 API Key 时应在构造阶段快速失败。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")

    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        LLMClient()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_chat_with_system_message() -> None:
    """验证包含 system 指令的多消息对话。"""
    client = LLMClient()
    request = LLMRequest(
        messages=[
            {
                "role": "system",
                "content": "你是一个严格简洁的助手，回答不超过 25 个字。",
            },
            {
                "role": "user",
                "content": "请描述 GIIM 的核心作用。",
            },
        ],
        max_tokens=120,
        temperature=0.3,
    )

    response = await client.chat(request)

    assert response.content.strip() != ""
    assert response.usage.total_tokens > 0
