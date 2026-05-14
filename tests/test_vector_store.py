"""Qdrant 向量存储客户端单元与集成测试。"""

from __future__ import annotations

import math
import os
import random
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from src.vector_store import (
    QdrantVectorStore,
    SearchRequest,
    UpsertRequest,
    VectorPoint,
)

VECTOR_DIM = 1024


def _make_admin_client() -> AsyncQdrantClient:
    """构造用于夹具清理的裸 AsyncQdrantClient。"""
    url = os.environ.get("QDRANT_URL", "http://qdrant:6333").strip()
    api_key = os.environ.get("QDRANT_API_KEY", "").strip()
    kwargs: dict[str, str] = {"url": url}
    if api_key:
        kwargs["api_key"] = api_key
    return AsyncQdrantClient(**kwargs)


def random_unit_vector(dim: int) -> list[float]:
    """生成均匀随机单位向量 (L2 归一化)。"""
    raw = [random.gauss(0.0, 1.0) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    if norm == 0.0:
        return random_unit_vector(dim)
    return [x / norm for x in raw]


def subtract_projection(base: list[float], vector: list[float]) -> list[float]:
    """从 vector 中减去在 base 方向上的投影分量。"""
    dot_bb = sum(b * b for b in base)
    if dot_bb == 0.0:
        return vector[:]
    dot_vb = sum(v * b for v, b in zip(vector, base, strict=True))
    scale = dot_vb / dot_bb
    return [v - scale * b for v, b in zip(vector, base, strict=True)]


def normalize(vector: list[float]) -> list[float]:
    """L2 归一化。"""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0:
        raise ValueError("零向量无法归一化")
    return [x / norm for x in vector]


@pytest_asyncio.fixture
async def isolated_vector_store(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[QdrantVectorStore]:
    """使用独立集合名并保证测试前后清理 Qdrant 集合。"""
    name = f"test_vector_store_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("QDRANT_COLLECTION_NAME", name)

    admin = _make_admin_client()
    try:
        if await admin.collection_exists(collection_name=name):
            await admin.delete_collection(collection_name=name)
    finally:
        await admin.close()

    yield QdrantVectorStore()

    admin2 = _make_admin_client()
    try:
        if await admin2.collection_exists(collection_name=name):
            await admin2.delete_collection(collection_name=name)
    finally:
        await admin2.close()


def test_invalid_distance_raises_at_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """非法 QDRANT_DISTANCE 应在初始化阶段抛出 ValueError (无需真实 Qdrant)。"""
    monkeypatch.setenv("QDRANT_DISTANCE", "invalid_distance")
    with pytest.raises(ValueError, match="QDRANT_DISTANCE"):
        QdrantVectorStore()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ensure_collection_creates_when_missing(
    isolated_vector_store: QdrantVectorStore,
) -> None:
    """集合不存在时应成功创建并匹配向量配置。"""
    name = os.environ["QDRANT_COLLECTION_NAME"]
    await isolated_vector_store.ensure_collection()

    admin = _make_admin_client()
    try:
        info = await admin.get_collection(collection_name=name)
        params = info.config.params
        assert params is not None and params.vectors is not None
        vectors = params.vectors
        if isinstance(vectors, models.VectorParams):
            assert vectors.size == VECTOR_DIM
            assert vectors.distance == models.Distance.COSINE
        else:
            first = next(iter(vectors.values()))
            assert first.size == VECTOR_DIM
            assert first.distance == models.Distance.COSINE
    finally:
        await admin.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ensure_collection_idempotent(isolated_vector_store: QdrantVectorStore) -> None:
    """连续两次 ensure_collection 应幂等且不抛错。"""
    await isolated_vector_store.ensure_collection()
    await isolated_vector_store.ensure_collection()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_upsert_single(isolated_vector_store: QdrantVectorStore) -> None:
    """写入单点后集合计数应增加 1。"""
    await isolated_vector_store.ensure_collection()
    before = await isolated_vector_store.count()

    point = VectorPoint(
        id=str(uuid.uuid4()),
        vector=random_unit_vector(VECTOR_DIM),
        payload={"title": "unit", "url": "https://example.com/a"},
    )
    response = await isolated_vector_store.upsert(UpsertRequest(points=[point]))

    assert response.count == 1
    assert await isolated_vector_store.count() == before + 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_returns_self(isolated_vector_store: QdrantVectorStore) -> None:
    """用已写入向量检索时,自身应排在首位且分数极高。"""
    await isolated_vector_store.ensure_collection()

    vectors = [random_unit_vector(VECTOR_DIM) for _ in range(5)]
    target_id = str(uuid.uuid4())
    points = [
        VectorPoint(
            id=target_id if index == 0 else str(uuid.uuid4()),
            vector=vec,
            payload={"idx": index},
        )
        for index, vec in enumerate(vectors)
    ]
    await isolated_vector_store.upsert(UpsertRequest(points=points))

    search = await isolated_vector_store.search(
        SearchRequest(query_vector=vectors[0], top_k=5),
    )
    assert search.results
    assert search.results[0].id == target_id
    assert search.results[0].score > 0.99


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_with_threshold(isolated_vector_store: QdrantVectorStore) -> None:
    """高 score_threshold 应过滤低相似度点。"""
    await isolated_vector_store.ensure_collection()

    base = random_unit_vector(VECTOR_DIM)
    noise = random_unit_vector(VECTOR_DIM)
    orth = normalize(subtract_projection(base, noise))
    near = normalize([base[i] + 0.05 * orth[i] for i in range(VECTOR_DIM)])
    far = orth

    id_near = str(uuid.uuid4())
    id_far = str(uuid.uuid4())
    await isolated_vector_store.upsert(
        UpsertRequest(
            points=[
                VectorPoint(id=str(uuid.uuid4()), vector=base, payload={"role": "base"}),
                VectorPoint(id=id_near, vector=near, payload={"role": "near"}),
                VectorPoint(id=id_far, vector=far, payload={"role": "far"}),
            ],
        ),
    )

    search = await isolated_vector_store.search(
        SearchRequest(query_vector=base, top_k=10, score_threshold=0.99),
    )
    returned_ids = {item.id for item in search.results}
    assert id_far not in returned_ids
    assert all(item.score >= 0.99 for item in search.results)
