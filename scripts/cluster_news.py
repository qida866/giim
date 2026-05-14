"""命令行入口:从 Qdrant 拉取新闻向量,使用 sklearn HDBSCAN 聚类并打印分析结果。

默认不写库;设置 CLUSTER_WRITE_TO_DB=true 时将聚类结果写入 Day 2 的 events / event_news 表。
编排逻辑见 Day 6 A 阶段设计草案 v2 与 Day 6 B 写库说明。

用法示例:
    docker compose exec api python -m scripts.cluster_news
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse
from sklearn.cluster import HDBSCAN

# 让 scripts 目录能 import src.xxx
PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from sqlalchemy import delete, select

from src.core.logging import get_logger
from src.db.session import AsyncSessionLocal
from src.models.event import Event, EventNews
from src.models.news import News

logger = get_logger(__name__)

EXPECTED_VECTOR_DIM = int(os.getenv("QDRANT_VECTOR_SIZE", "1024").strip())


@dataclass(frozen=True)
class ClusterConfig:
    """聚类脚本可调参数 (来自环境变量)。"""
    min_cluster_size: int
    min_samples: int
    write_to_db: bool


def load_cluster_config() -> ClusterConfig:
    """解析 CLUSTER_* 环境变量,非法则抛出 ValueError。"""
    raw_size = os.getenv("CLUSTER_MIN_SIZE", "5").strip()
    raw_samples = os.getenv("CLUSTER_MIN_SAMPLES", "3").strip()
    try:
        min_cluster_size = int(raw_size)
    except ValueError as exc:
        raise ValueError(f"CLUSTER_MIN_SIZE 非法: {raw_size!r}") from exc
    try:
        min_samples = int(raw_samples)
    except ValueError as exc:
        raise ValueError(f"CLUSTER_MIN_SAMPLES 非法: {raw_samples!r}") from exc

    if min_cluster_size < 2 or min_cluster_size > 50:
        raise ValueError(f"CLUSTER_MIN_SIZE 须在 2-50 之间,当前为 {min_cluster_size}")
    if min_samples < 1 or min_samples > 50:
        raise ValueError(f"CLUSTER_MIN_SAMPLES 须在 1-50 之间,当前为 {min_samples}")

    if min_samples > min_cluster_size:
        logger.warning(
            "cluster_hdbscan_param_hint",
            message="sklearn 文档建议 min_samples <= min_cluster_size",
            min_samples=min_samples,
            min_cluster_size=min_cluster_size,
        )

    write_to_db = os.getenv("CLUSTER_WRITE_TO_DB", "false").strip().lower() == "true"

    return ClusterConfig(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        write_to_db=write_to_db,
    )


def _extract_vector(record: models.Record) -> list[float] | None:
    """从 scroll 返回的 Record 中取出默认向量;无或无法解析则返回 None。"""
    raw = record.vector
    if raw is None:
        return None
    if isinstance(raw, list):
        if not raw:
            return None
        return [float(x) for x in raw]
    if isinstance(raw, dict):
        if not raw:
            return None
        first = next(iter(raw.values()))
        if first is None:
            return None
        if isinstance(first, list):
            return [float(x) for x in first]
        return None
    return None


def _title_from_record(record: models.Record) -> str:
    """从 payload 读取 title;缺失时用占位。"""
    payload = record.payload
    if not isinstance(payload, dict):
        return "(无标题)"
    title = payload.get("title")
    if title is None or str(title).strip() == "":
        return "(无标题)"
    return str(title)


async def scroll_all_points(
    client: AsyncQdrantClient,
    collection_name: str,
) -> list[models.Record]:
    """使用 scroll 拉取集合内全部点,必须携带向量。"""
    out: list[models.Record] = []
    offset: models.PointId | None = None
    while True:
        records, next_offset = await client.scroll(
            collection_name=collection_name,
            limit=256,
            with_vectors=True,
            with_payload=True,
            offset=offset,
        )
        out.extend(records)
        if next_offset is None:
            break
        offset = next_offset
    return out


def build_matrix_and_titles(
    records: list[models.Record],
) -> tuple[NDArray[np.float64], list[str]]:
    """将 Record 列表转为 (N, D) 矩阵与 title 列表;无向量或维度非法则抛出 ValueError。"""
    missing = 0
    vectors: list[list[float]] = []
    titles: list[str] = []

    for rec in records:
        vec = _extract_vector(rec)
        if vec is None:
            missing += 1
            continue
        vectors.append(vec)
        titles.append(_title_from_record(rec))

    if missing > 0:
        raise ValueError(f"Qdrant 集合中 {missing} 个 point 无向量, 数据完整性异常")

    if not vectors:
        raise ValueError("无有效向量可构建矩阵")

    for i, vec in enumerate(vectors):
        if len(vec) != EXPECTED_VECTOR_DIM:
            raise ValueError(
                f"向量维度异常: 期望 {EXPECTED_VECTOR_DIM}, 第 {i} 条实际为 {len(vec)}",
            )

    matrix = np.asarray(vectors, dtype=np.float64)
    return matrix, titles


def print_clustering_report(
    labels: np.ndarray,
    titles: list[str],
    *,
    top_n: int = 10,
    sample_titles: int = 3,
) -> None:
    """打印聚类统计与 Top 大簇样例标题 (标准输出)。"""
    n = int(labels.shape[0])
    noise_mask = labels == -1
    noise_count = int(np.sum(noise_mask))
    non_noise = labels[~noise_mask]
    cluster_count = int(np.unique(non_noise).size) if non_noise.size > 0 else 0

    cluster_sizes: Counter[int] = Counter()
    for lab in labels:
        if lab != -1:
            cluster_sizes[int(lab)] += 1

    noise_pct = (100.0 * noise_count / n) if n > 0 else 0.0
    if cluster_count > 0:
        avg_size = (n - noise_count) / cluster_count
        avg_line = f"{avg_size:.1f} 条"
    else:
        avg_line = "N/A"

    print("============== 聚类结果 ==============")
    print(f"总点数: {n}")
    print(f"簇数: {cluster_count}")
    print(f"噪声点: {noise_count} ({noise_pct:.1f}%)")
    print(f"平均簇大小: {avg_line}")
    print(f"============== Top {top_n} 大簇 ==============")

    top_clusters = cluster_sizes.most_common(top_n)
    for cid, size in top_clusters:
        print(f"Cluster {cid}: {size} 条")
        print()
        idxs = [i for i in range(n) if int(labels[i]) == cid][:sample_titles]
        for j in idxs:
            print(titles[j])
        print()


def _news_id_from_record(record: models.Record) -> int:
    """从 Qdrant payload 解析 news_id。"""
    payload = record.payload
    if not isinstance(payload, dict) or "news_id" not in payload:
        raise ValueError("Qdrant payload 缺少 news_id")
    return int(payload["news_id"])


async def persist_clusters_to_db(
    records: list[models.Record],
    labels: NDArray[np.int64],
    titles: list[str],
) -> dict[str, int]:
    """把聚类结果写入 events + event_news 表. 返回统计 (event_count / link_count)。"""
    event_count = 0
    link_count = 0
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(delete(EventNews))
            await session.execute(delete(Event))
            await session.commit()
            logger.info(
                "cluster_db_cleared",
                message="已清空 event_news 与 events,准备写入本轮 hdbscan 聚类",
            )

            for cluster_label in np.unique(labels):
                if int(cluster_label) == -1:
                    continue
                cluster_indices = [i for i, lab in enumerate(labels) if int(lab) == int(cluster_label)]
                if not cluster_indices:
                    continue
                cluster_news_ids = [_news_id_from_record(records[i]) for i in cluster_indices]
                cluster_titles = [titles[i] for i in cluster_indices]

                unique_ids = list(dict.fromkeys(cluster_news_ids))
                stmt = select(News.id, News.published_at).where(News.id.in_(unique_ids))
                result = await session.execute(stmt)
                rows = result.all()
                if len(rows) != len(unique_ids):
                    raise ValueError(
                        f"簇 {cluster_label} 中部分 news_id 在 PostgreSQL 中不存在 "
                        f"(期望 {len(unique_ids)} 条,实际查到 {len(rows)} 条)",
                    )
                published_by_id = {int(r[0]): r[1] for r in rows}
                published_list = [published_by_id[nid] for nid in cluster_news_ids]
                first_seen = min(published_list)
                last_updated = max(published_list)
                representative_title = cluster_titles[0]
                title_db = representative_title[:500]

                event = Event(
                    title=title_db,
                    summary=None,
                    status="active",
                    first_seen_at=first_seen,
                    last_updated_at=last_updated,
                    news_count=len(cluster_news_ids),
                    tags=None,
                )
                session.add(event)
                await session.flush()

                for news_id in cluster_news_ids:
                    session.add(
                        EventNews(
                            event_id=event.id,
                            news_id=news_id,
                            similarity_score=None,
                            cluster_method="hdbscan",
                        ),
                    )
                    link_count += 1
                event_count += 1

            await session.commit()
            logger.info(
                "cluster_db_persisted",
                event_count=event_count,
                link_count=link_count,
                message="聚类结果已写入数据库",
            )
        except Exception:
            await session.rollback()
            raise

    return {"event_count": event_count, "link_count": link_count}


async def main() -> int:
    """执行聚类分析主流程,返回进程退出码 (0 成功,1 失败)。"""
    try:
        cfg = load_cluster_config()
    except ValueError as exc:
        logger.error(
            "cluster_config_invalid",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return 1

    collection_name = os.getenv("QDRANT_COLLECTION_NAME", "news_embeddings").strip()
    if not collection_name:
        logger.error(
            "cluster_collection_name_empty",
            message="QDRANT_COLLECTION_NAME 不能为空",
        )
        return 1

    url = os.getenv("QDRANT_URL", "http://qdrant:6333").strip()
    api_key = os.getenv("QDRANT_API_KEY", "").strip()
    kwargs: dict[str, Any] = {"url": url}
    if api_key:
        kwargs["api_key"] = api_key
    client = AsyncQdrantClient(**kwargs)

    try:
        try:
            await client.get_collection(collection_name=collection_name)
        except UnexpectedResponse as exc:
            if exc.status_code == 404:
                logger.error(
                    "cluster_collection_not_found",
                    collection_name=collection_name,
                    message="Qdrant 集合不存在",
                )
                return 1
            raise

        records = await scroll_all_points(client, collection_name)
        if len(records) == 0:
            logger.warning(
                "cluster_no_points",
                collection_name=collection_name,
                message="集合中无点,跳过聚类",
            )
            return 1

        try:
            matrix, titles = build_matrix_and_titles(records)
        except ValueError as exc:
            msg = str(exc)
            if "无向量" in msg and "数据完整性异常" in msg:
                logger.error(
                    "cluster_integrity_missing_vectors",
                    message=msg,
                )
            else:
                logger.error(
                    "cluster_matrix_build_failed",
                    error_type=type(exc).__name__,
                    error_message=msg,
                )
            return 1

        # bge-m3 向量已 L2 normalize,欧氏距离与余弦在该前提下等价;sklearn HDBSCAN 无原生 cosine。
        clusterer = HDBSCAN(
            min_cluster_size=cfg.min_cluster_size,
            min_samples=cfg.min_samples,
            metric="euclidean",
        )
        labels = clusterer.fit_predict(matrix)
        labels_i64 = labels.astype(np.int64, copy=False)

        print_clustering_report(labels_i64, titles, top_n=10, sample_titles=3)

        if cfg.write_to_db:
            try:
                result = await persist_clusters_to_db(records, labels_i64, titles)
                logger.info("cluster_persist_completed", **result)
            except Exception as exc:  # noqa: BLE001 - 写库失败需记录后退出
                logger.error(
                    "cluster_persist_failed",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                return 1

        logger.info(
            "cluster_run_completed",
            point_count=int(matrix.shape[0]),
            message="聚类分析完成",
        )
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
