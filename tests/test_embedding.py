"""Embedding 客户端集成测试。"""

from __future__ import annotations

import math

import pytest

from src.embedding import EmbeddingClient, EmbeddingRequest

EXPECTED_DIMENSION = 1024  # bge-m3 维度


@pytest.fixture(scope="module")
def embedding_client() -> EmbeddingClient:
    """提供模块级 EmbeddingClient，避免重复加载模型。"""
    return EmbeddingClient()


def cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    """计算两条向量的余弦相似度。"""
    dot = sum(a * b for a, b in zip(vector_a, vector_b, strict=True))
    norm_a = math.sqrt(sum(a * a for a in vector_a))
    norm_b = math.sqrt(sum(b * b for b in vector_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_embed_single(embedding_client: EmbeddingClient) -> None:
    """单条文本应返回 1024 维向量。"""
    request = EmbeddingRequest(
        texts=["全球市场关注美联储最新利率决议。"],
        normalize=True,
    )

    response = await embedding_client.embed(request)

    assert len(response.results) == 1
    assert response.results[0].dimension == EXPECTED_DIMENSION
    assert len(response.results[0].vector) == EXPECTED_DIMENSION
    assert response.model_name.strip() != ""


@pytest.mark.asyncio
@pytest.mark.integration
async def test_embed_batch(embedding_client: EmbeddingClient) -> None:
    """批量文本应保持输入输出条数一致。"""
    input_texts = [
        "美联储宣布降息，市场情绪回暖。",
        "欧盟讨论新的能源安全政策框架。",
        "东南亚多国推进跨境数字支付合作。",
    ]
    request = EmbeddingRequest(texts=input_texts, normalize=True)

    response = await embedding_client.embed(request)

    assert len(response.results) == len(input_texts)
    for index, result in enumerate(response.results):
        assert result.text == input_texts[index]
        assert result.dimension == EXPECTED_DIMENSION
        assert len(result.vector) == EXPECTED_DIMENSION


@pytest.mark.asyncio
@pytest.mark.integration
async def test_embed_semantic_similarity(embedding_client: EmbeddingClient) -> None:
    """跨语言相似语句应具备较高语义相似度。"""
    request = EmbeddingRequest(
        texts=[
            "美联储宣布降息",
            "Fed cuts interest rates",
        ],
        normalize=True,
    )

    response = await embedding_client.embed(request)

    vector_a = response.results[0].vector
    vector_b = response.results[1].vector
    similarity = cosine_similarity(vector_a, vector_b)

    assert response.results[0].dimension == EXPECTED_DIMENSION
    assert response.results[1].dimension == EXPECTED_DIMENSION
    assert similarity > 0.7
