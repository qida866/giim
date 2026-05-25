"""GIIM 基础 CLI: 今日 Top 事件、单事件详情、语义搜索等子命令.

用法:
    docker compose exec api python -m scripts.cli today [--limit N]
    docker compose exec api python -m scripts.cli show <event_id> [--news-limit N]
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

from sqlalchemy import String, cast, desc, func, select

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
TODAY_LIMIT_MIN = 1
TODAY_LIMIT_MAX = 50
SHOW_NEWS_LIMIT_MIN = 1
SHOW_NEWS_LIMIT_MAX = 20
UUID_HEX_LEN = 32


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


def _iso_week_key(dt: datetime) -> str:
    """将时间戳转为 ISO 周键 (与 cluster_news 一致)。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc_dt = dt.astimezone(timezone.utc)
    year, week, _ = utc_dt.isocalendar()
    return f"{year}-W{week:02d}"


def _event_span_days(first_seen_at: datetime, last_updated_at: datetime) -> int:
    """首发至末更跨越的自然日数 (至少 1)。"""
    d1 = first_seen_at.astimezone(timezone.utc).date()
    d2 = last_updated_at.astimezone(timezone.utc).date()
    return max(1, (d2 - d1).days + 1)


def _normalize_uuid_hex(raw: str) -> str:
    """校验并规范化 UUID 参数为 32 位小写 hex (无连字符)。"""
    s = raw.strip().lower()
    hex_only = s.replace("-", "")
    if not hex_only or len(hex_only) > UUID_HEX_LEN:
        msg = f"event_id 须为 1-{UUID_HEX_LEN} 位十六进制 (可含连字符)"
        raise ValueError(msg)
    if not all(c in "0123456789abcdef" for c in hex_only):
        raise ValueError("event_id 仅允许 0-9、a-f 及连字符")
    return hex_only


def _format_impact_factors(raw: dict | None) -> str:
    """将 impact_factors JSONB 格式化为评分细节行。"""
    if not isinstance(raw, dict):
        return "(无评分细节)"
    keys = ("source_count", "authority", "recency", "duration")
    parts: list[str] = []
    for key in keys:
        val = raw.get(key)
        if isinstance(val, (int, float)):
            parts.append(f"{key}={float(val):.2f}")
        else:
            parts.append(f"{key}=-")
    return " | ".join(parts)


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


async def _resolve_event(session, hex_id: str) -> Event | None:
    """按完整 UUID 或 hex 前缀解析唯一事件; 无匹配或多匹配返回 None 并打印提示。"""
    if len(hex_id) == UUID_HEX_LEN:
        try:
            uid = uuid.UUID(hex=hex_id)
        except ValueError:
            print("无效的 UUID")
            return None
        stmt = select(Event).where(Event.id == uid)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()
        if event is None:
            print(f"未找到事件: {hex_id}")
        return event

    pattern = f"{hex_id}%"
    stmt = select(Event).where(cast(Event.id, String).like(pattern))
    result = await session.execute(stmt)
    matches: list[Event] = list(result.scalars().all())
    if not matches:
        print(f"未找到前缀匹配的事件: {hex_id}")
        return None
    if len(matches) > 1:
        print(f"前缀 '{hex_id}' 匹配到 {len(matches)} 个事件, 请加长前缀:")
        for ev in matches[:10]:
            print(f"  {ev.id}")
        if len(matches) > 10:
            print(f"  ... 另有 {len(matches) - 10} 个")
        return None
    return matches[0]


async def _fetch_show_news(
    session,
    event_id: uuid.UUID,
    limit: int,
) -> list[tuple[News, str]]:
    """JOIN event_news + news, 按 published_at 降序取前 N 条。"""
    stmt = (
        select(News, EventNews.cluster_method)
        .join(EventNews, EventNews.news_id == News.id)
        .where(EventNews.event_id == event_id)
        .order_by(desc(News.published_at))
        .limit(limit)
    )
    rows = await session.execute(stmt)
    return [(row[0], str(row[1])) for row in rows.all()]


async def _fetch_sources_count(session, event_id: uuid.UUID) -> int:
    """统计事件关联新闻的去重来源数。"""
    stmt = (
        select(func.count(func.distinct(News.source_name)))
        .select_from(EventNews)
        .join(News, EventNews.news_id == News.id)
        .where(EventNews.event_id == event_id)
    )
    val = await session.scalar(stmt)
    return int(val or 0)


def _print_show_header() -> None:
    """打印事件详情页眉。"""
    sep = "═" * 55
    print(sep)
    print("GIIM 事件详情")
    print(sep)


def _print_show_footer() -> None:
    """打印事件详情页脚。"""
    print("═" * 55)


def _print_show_news_block(rank: int, item: News) -> None:
    """打印单条原始新闻块。"""
    pub = _format_date_utc(item.published_at)
    source = item.source_name or "未知来源"
    print(f"\n#{rank}  [{source}] {pub}")
    print(f"    📰 {item.title}")
    print(f"    🔗 {item.source_url}")
    snippet = _normalize_content(item.content)
    print(f"    内容前 200 字: {snippet}")


def _print_show_detail(
    event: Event,
    sources_count: int,
    cluster_method: str,
    news_rows: list[tuple[News, str]],
    news_limit: int,
) -> None:
    """渲染单事件深度视图。"""
    score = float(event.impact_score) if event.impact_score is not None else 0.0
    stars = stars_for_score(score)
    label = event_type_label(event.event_type)
    dur = duration_str(event.first_seen_at, event.last_updated_at)
    d1 = _format_date_utc(event.first_seen_at)
    d2 = _format_date_utc(event.last_updated_at)
    span_days = _event_span_days(event.first_seen_at, event.last_updated_at)
    week_key = _iso_week_key(event.first_seen_at)

    _print_show_header()
    print(f"ID:       {event.id}")
    print(f"标题:     {event.title}")
    print(f"类型:     {label}  时长: {dur}")
    print(f"影响力:   {stars} {score:.2f}")
    print(f"评分细节: {_format_impact_factors(event.impact_factors)}")
    print()
    print("摘要 (LLM 生成):")
    summary = event.summary
    if summary is None or not str(summary).strip():
        print("(暂无摘要)")
    else:
        for line in str(summary).splitlines():
            print(line)
    print()
    print(f"时间:     {d1} ~ {d2} ({span_days} 天)")
    print(
        f"覆盖:     {event.news_count} 家媒体 / {sources_count} 个来源",
    )
    print(f"聚类方法: {cluster_method} ({week_key})")
    print()
    print(f"原始新闻 (前 {news_limit} 条, 按时间倒序):")
    if not news_rows:
        print("(无关联新闻)")
    else:
        for rank, (news_item, _) in enumerate(news_rows, start=1):
            _print_show_news_block(rank, news_item)
    print()
    _print_show_footer()


async def cmd_show(event_id_raw: str, news_limit: int) -> int:
    """按 UUID 或前缀查询单事件并打印深度视图。"""
    try:
        hex_id = _normalize_uuid_hex(event_id_raw)
    except ValueError as exc:
        print(str(exc))
        return 1

    async with AsyncSessionLocal() as session:
        event = await _resolve_event(session, hex_id)
        if event is None:
            return 1

        news_rows = await _fetch_show_news(session, event.id, news_limit)
        sources_count = await _fetch_sources_count(session, event.id)
        cluster_method = news_rows[0][1] if news_rows else "—"

        _print_show_detail(
            event,
            sources_count,
            cluster_method,
            news_rows,
            news_limit,
        )
    return 0


async def cmd_today(limit: int) -> int:
    """查询并打印今日 Top N (有影响力分的事件)。"""
    async with AsyncSessionLocal() as session:
        total_events = await session.scalar(select(func.count()).select_from(Event))
        if total_events is None or int(total_events) == 0:
            print("警告: events 表为空, 无法展示今日头条。")
            return 1

        stmt = (
            select(Event)
            .where(Event.impact_score.is_not(None))
            .order_by(desc(Event.impact_score).nulls_last())
            .limit(limit)
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
    today_parser = sub.add_parser("today", help="显示 Top 事件 (按 impact_score 降序)")
    today_parser.add_argument(
        "--limit",
        type=int,
        default=15,
        help=f"返回条数 ({TODAY_LIMIT_MIN}-{TODAY_LIMIT_MAX}, 默认 15)",
    )
    show_parser = sub.add_parser("show", help="显示单事件深度视图")
    show_parser.add_argument(
        "event_id",
        help="事件 UUID (完整或十六进制前缀)",
    )
    show_parser.add_argument(
        "--news-limit",
        type=int,
        default=5,
        help=f"原始新闻条数 ({SHOW_NEWS_LIMIT_MIN}-{SHOW_NEWS_LIMIT_MAX}, 默认 5)",
    )
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
        if not TODAY_LIMIT_MIN <= args.limit <= TODAY_LIMIT_MAX:
            parser.error(f"--limit 须在 {TODAY_LIMIT_MIN}-{TODAY_LIMIT_MAX} 之间")
        return await cmd_today(args.limit)

    if args.command == "show":
        if not SHOW_NEWS_LIMIT_MIN <= args.news_limit <= SHOW_NEWS_LIMIT_MAX:
            parser.error(
                f"--news-limit 须在 {SHOW_NEWS_LIMIT_MIN}-{SHOW_NEWS_LIMIT_MAX} 之间",
            )
        return await cmd_show(args.event_id, args.news_limit)

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
