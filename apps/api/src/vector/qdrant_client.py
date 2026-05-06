"""Qdrant 客户端封装模块，提供基础向量操作能力。"""

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.core.config import settings
from src.core.exceptions import VectorStoreError


class QdrantClientWrapper:
    """Qdrant 客户端基础封装。"""

    def __init__(self) -> None:
        self._client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)

    @property
    def client(self) -> QdrantClient:
        """返回底层 Qdrant 客户端。"""
        return self._client

    def ensure_collection(self, name: str, vector_size: int) -> None:
        """确保集合存在，不存在则创建。"""
        try:
            collections = self._client.get_collections()
            exists = any(item.name == name for item in collections.collections)
            if not exists:
                self._client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
                )
        except UnexpectedResponse as exc:
            raise VectorStoreError("创建或检查 Qdrant 集合失败", detail=str(exc)) from exc

    def upsert(self, collection: str, points: list[PointStruct]) -> None:
        """向指定集合写入向量点。"""
        try:
            self._client.upsert(collection_name=collection, points=points)
        except UnexpectedResponse as exc:
            raise VectorStoreError("写入 Qdrant 向量数据失败", detail=str(exc)) from exc

    def search(self, collection: str, vector: list[float], limit: int) -> list[dict]:
        """在指定集合执行向量检索。"""
        try:
            result = self._client.search(
                collection_name=collection,
                query_vector=vector,
                limit=limit,
            )
            return [item.model_dump() for item in result]
        except UnexpectedResponse as exc:
            raise VectorStoreError("检索 Qdrant 向量数据失败", detail=str(exc)) from exc
