"""GIIM 基础 CLI: 今日 Top 事件、语义搜索等子命令.

用法:
    docker compose exec api python -m scripts.cli today
    docker compose exec api python -m scripts.cli search "AI 芯片" --limit 5

展示辅助已抽到 src.utils.display; score_events_impact 仍待去重。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import desc, func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.db.session import AsyncSessionLocal
from src.embedding import EmbeddingClient, EmbeddingError, EmbeddingRequest
from src.models.event import Event, EventNews
from src.models.news import News
from src.utils.display import duration_str, event_type_label, stars_for_score
from src.vector_store import QdrantVectorStore, SearchRequest, SearchResult, VectorStoreError

KEYWORD_MAX_LEN = 500
SEARCH_LIMIT_MIN = 1
SEARCH_LIMIT_MAX = 50


def _format_date_utc(dt: datetime) -> str:
    """转为 UTC 日期 ISO 字符串用于展示。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date().isoformat()


def _print_today_header(n: int) -> None:
    """打印今日视图页眉。"""
    sep = "═" * 55
    print(sep)
    print("GIIM - 全球新闻智能监测")
    print(sep)
    print(f"今日 Top {n} 重要事件 (按影响力排序)")
    print(sep)


def _print_event_block(rank: int, event: Event, sources_count: int) -> None:
    """打印单条事件的格式化块。"""
    score = float(event.impact_score) if event.impact_score is not None else 0.0
    stars = stars_for_score(score)
    label = event_type_label(event.event_type)
    d1 = _format_date_utc(event.first_seen_at)
    d2 = _format_date_utc(event.last_updated_at)
    dur = duration_str(event.first_seen_at, event.last_updated_at)

    print(f"\n#{rank}  {stars} {label} {score:.2f}")
    print(f"    📰 {event.title}")
    print(
        f"    📅 {d1} ~ {d2} ({dur}) · 来自 {event.news_count} 家媒体 / {sources_count} 个来源"
    )
    print()
    summary = event.summary
    if summary is None or not str(summary).strip():
        print("    (暂无摘要)")
    else:
        for line in str(summary).splitlines():
            print(f"    {line}")
    print()
    print("─" * 55)


def _normalize_content(text: str, max_len: int = 200) -> str:
    """将正文截断并压成单行。"""
    one_line = " ".join(text.split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[:max_len]


def _parse_published_date(iso_str: str) -> str:
    """将 ISO 时间串转为 YYYY-MM-DD。"""
    if not iso_str.strip():
        return ""
    try:
        normalized = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).date().isoformat()
    except ValueError:
        return iso_str[:10] if len(iso_str) >= 10 else iso_str


def _hit_display_fields(result: SearchResult) -> dict[str, str | float | int | None]:
    """从 SearchResult payload 提取展示字段。"""
    payload = result.payload
    raw_news_id = payload.get("news_id", result.id)
    try:
        news_id = int(raw_news_id)
    except (TypeError, ValueError):
        news_id = None
    return {
        "news_id": news_id,
        "title": str(payload.get("title", "")),
        "source": str(payload.get("source", "")),
        "published_at": str(payload.get("published_at", "")),
        "score": float(result.score),
    }


async def _fetch_contents_by_ids(news_ids: list[int]) -> dict[int, str]:
    """批量查询新闻正文 (Qdrant payload 不含 content)。"""
    if not news_ids:
        return {}
    async with AsyncSessionLocal() as session:
        stmt = select(News.id, News.content).where(News.id.in_(news_ids))
        rows = await session.execute(stmt)
        return {int(row[0]): str(row[1] or "") for row in rows.all()}


def _print_search_header(keyword: str, count: int) -> None:
    """打印搜索页眉。"""
    sep = "═" * 55
    print(sep)
    print(f'GIIM 搜索: "{keyword}"')
    print(sep)
    print(f"找到 {count} 条相关新闻 (按语义相似度排序)")
    print(sep)


def _print_search_block(
    rank: int,
    score: float,
    published_date: str,
    source: str,
    title: str,
    content_snippet: str,
) -> None:
    """打印单条搜索命中。"""
    date_part = published_date or "未知日期"
    source_part = source or "未知来源"
    print(f"\n#{rank}  [相似度 {score:.2f}] {date_part} · {source_part}")
    print(f"    📰 {title}")
    print(f"    {content_snippet}")
    print()
    print("─" * 55)


def _print_search_footer(keyword: str, count: int, duration_ms: int) -> None:
    """打印搜索页脚。"""
    sep = "═" * 55
    print(sep)
    print(
        f'GIIM 搜索完成 | 关键词: "{keyword}" | 命中 {count} 条 | 耗时 {duration_ms}ms'
    )
    print(sep)


async def cmd_search(keyword: str, limit: int) -> int:
    """语义搜索新闻并打印结果。"""
    embedder = EmbeddingClient()
    store = QdrantVectorStore()
    total_duration_ms = 0

    try:
        embed_out = await embedder.embed(
            EmbeddingRequest(texts=[keyword], normalize=True),
        )
        total_duration_ms += embed_out.duration_ms
    except EmbeddingError as exc:
        print(f"向量化失败: {exc.error_type.value}")
        return 1

    if not embed_out.results:
        print("向量化未返回结果")
        return 1

    try:
        search_out = await store.search(
            SearchRequest(
                query_vector=embed_out.results[0].vector,
                top_k=limit,
            ),
        )
        total_duration_ms += search_out.duration_ms
    except VectorStoreError as exc:
        print(f"向量检索失败: {exc.error_type.value}")
        return 1

    results = search_out.results
    if not results:
        _print_search_header(keyword, 0)
        print("\n未找到相关新闻")
        return 0

    news_ids: list[int] = []
    for hit in results:
        fields = _hit_display_fields(hit)
        raw_id = fields["news_id"]
        if isinstance(raw_id, int):
            news_ids.append(raw_id)

    try:
        content_by_id = await _fetch_contents_by_ids(news_ids)
    except Exception as exc:  # noqa: BLE001 - CLI 统一兜底 DB 异常
        print(f"数据库查询失败: {exc}")
        return 1

    _print_search_header(keyword, len(results))

    for rank, hit in enumerate(results, start=1):
        fields = _hit_display_fields(hit)
        news_id = fields["news_id"]
        raw_content = ""
        if isinstance(news_id, int):
            raw_content = content_by_id.get(news_id, "")
        if raw_content.strip():
            snippet = _normalize_content(raw_content)
        else:
            snippet = "(无正文)"

        _print_search_block(
            rank=rank,
            score=float(fields["score"]),
            published_date=_parse_published_date(str(fields["published_at"])),
            source=str(fields["source"]),
            title=str(fields["title"]),
            content_snippet=snippet,
        )

    _print_search_footer(keyword, len(results), total_duration_ms)
    return 0


async def cmd_today() -> int:
    """查询并打印今日 Top 15 (有影响力分的事件)。"""
    async with AsyncSessionLocal() as session:
        total_events = await session.scalar(select(func.count()).select_from(Event))
        if total_events is None or int(total_events) == 0:
            print("警告: events 表为空, 无法展示今日头条。")
            return 1

        stmt = (
            select(Event)
            .where(Event.impact_score.is_not(None))
            .order_by(desc(Event.impact_score).nulls_last())
            .limit(15)
        )
        result = await session.execute(stmt)
        rows: list[Event] = list(result.scalars().all())
        n = len(rows)

        event_ids = [e.id for e in rows]
        sources_map: dict[uuid.UUID, int] = {}
        if event_ids:
            sources_stmt = (
                select(EventNews.event_id, func.count(func.distinct(News.source_name)))
                .select_from(EventNews)
                .join(News, EventNews.news_id == News.id)
                .where(EventNews.event_id.in_(event_ids))
                .group_by(EventNews.event_id)
            )
            sources_result = await session.execute(sources_stmt)
            sources_map = {row[0]: int(row[1]) for row in sources_result.all()}

        _print_today_header(n)

        for rank, event in enumerate(rows, start=1):
            sc = sources_map.get(event.id, 0)
            _print_event_block(rank, event, sc)

        news_total = await session.scalar(select(func.count()).select_from(News))
        sources_total = await session.scalar(
            select(func.count(func.distinct(News.source_name))).select_from(News)
        )

        events_count = int(total_events)
        news_count = int(news_total or 0)
        sources_count = int(sources_total or 0)

        print("═" * 55)
        print(
            f"GIIM 数据: {events_count} 个事件 | {news_count} 条新闻 | {sources_count} 个来源"
        )
        print("═" * 55)

    return 0


def _build_parser() -> argparse.ArgumentParser:
    """构造 CLI 解析器。"""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.cli",
        description="GIIM 命令行工具",
    )
    sub = parser.add_subparsers(dest="command", required=True, help="子命令")
    sub.add_parser("today", help="显示 Top 15 事件 (按 impact_score 降序)")
    search_parser = sub.add_parser("search", help="语义搜索新闻")
    search_parser.add_argument("keyword", help="搜索关键词")
    search_parser.add_argument(
        "-k",
        "--limit",
        type=int,
        default=10,
        help=f"返回条数 ({SEARCH_LIMIT_MIN}-{SEARCH_LIMIT_MAX})",
    )
    return parser


async def main_async(argv: list[str] | None = None) -> int:
    """异步入口: 解析参数并分发子命令。"""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "today":
        return await cmd_today()

    if args.command == "search":
        keyword = args.keyword.strip()
        if not keyword:
            parser.error("keyword 不能为空")
        if len(keyword) > KEYWORD_MAX_LEN:
            print(f"关键词长度不能超过 {KEYWORD_MAX_LEN} 字")
            return 1
        if not SEARCH_LIMIT_MIN <= args.limit <= SEARCH_LIMIT_MAX:
            parser.error(f"--limit 须在 {SEARCH_LIMIT_MIN}-{SEARCH_LIMIT_MAX} 之间")
        return await cmd_search(keyword, args.limit)

    parser.error(f"未知子命令: {args.command}")
    return 2


def main() -> int:
    """进程入口。"""
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
