"""GIIM 基础 CLI: 今日 Top 事件等子命令 (Day 7 Phase 4).

用法:
    docker compose exec api python -m scripts.cli today

TODO: 将 _stars_for_score / EVENT_TYPE_LABELS 与 score_events_impact 抽到公共 utils, 去重。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import desc, func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.db.session import AsyncSessionLocal
from src.models.event import Event
from src.models.news import News

# TODO(DRY): 与 scripts/score_events_impact.py 重复, 后续抽到 scripts/impact_display.py 等
EVENT_TYPE_LABELS: dict[str, str] = {"breaking": "[突发]", "ongoing": "[进行]", "topic": "[话题]"}


def _stars_for_score(score: float) -> str:
    """将总分映射为 5 星字符串 (含空星 ☆)。"""
    if score >= 0.8:
        return "★★★★★"
    if score >= 0.6:
        return "★★★★☆"
    if score >= 0.4:
        return "★★★☆☆"
    if score >= 0.2:
        return "★★☆☆☆"
    return "★☆☆☆☆"


def _event_type_label(event_type: str | None) -> str:
    """event_type 英文字段转终端中文标签 (含方括号)。"""
    if event_type is None:
        return "[?]"
    return EVENT_TYPE_LABELS.get(event_type, f"[{event_type}]")


def _format_date_utc(dt: datetime) -> str:
    """转为 UTC 日期 ISO 字符串用于展示。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date().isoformat()


def _duration_str(first_seen_at: datetime, last_updated_at: datetime) -> str:
    """首发至末更的时间跨度中文描述。"""
    diff: timedelta = last_updated_at - first_seen_at
    if diff < timedelta(days=1):
        return "今天"
    if diff < timedelta(days=7):
        return f"{diff.days} 天"
    return f"{diff.days} 天 (长期话题)"


def _print_today_header(n: int) -> None:
    """打印今日视图页眉。"""
    sep = "═" * 55
    print(sep)
    print("GIIM - 全球新闻智能监测")
    print(sep)
    print(f"今日 Top {n} 重要事件 (按影响力排序)")
    print(sep)


def _print_event_block(rank: int, event: Event) -> None:
    """打印单条事件的格式化块。"""
    score = float(event.impact_score) if event.impact_score is not None else 0.0
    stars = _stars_for_score(score)
    label = _event_type_label(event.event_type)
    d1 = _format_date_utc(event.first_seen_at)
    d2 = _format_date_utc(event.last_updated_at)
    dur = _duration_str(event.first_seen_at, event.last_updated_at)

    print(f"\n#{rank}  {stars} {label} {score:.2f}")
    print(f"    📰 {event.title}")
    print(
        f"    📅 {d1} ~ {d2} ({dur}) · 来自 {event.news_count} 家媒体"
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

        _print_today_header(n)

        for rank, event in enumerate(rows, start=1):
            _print_event_block(rank, event)

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
    """构造 CLI 解析器 (仅 today, Week 2 再扩展)。"""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.cli",
        description="GIIM 命令行工具",
    )
    sub = parser.add_subparsers(dest="command", required=True, help="子命令")
    sub.add_parser("today", help="显示 Top 15 事件 (按 impact_score 降序)")
    return parser


async def main_async(argv: list[str] | None = None) -> int:
    """异步入口: 解析参数并分发子命令。"""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "today":
        return await cmd_today()

    parser.error(f"未知子命令: {args.command}")
    return 2


def main() -> int:
    """进程入口。"""
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
