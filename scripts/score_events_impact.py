"""命令行入口: 全量重算 events 影响力评分并写回 PostgreSQL, 打印 Top 15。

设计见 Day 7 A: 0.4×来源数 + 0.3×权威 + 0.2×时效 + 0.1×跨度; 静态白名单。

用法: docker compose exec api python -m scripts.score_events_impact
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.core.logging import get_logger
from src.db.session import AsyncSessionLocal
from src.models.event import Event, EventNews
from src.models.news import News

logger = get_logger(__name__)

CHINESE_AUTHORITY: frozenset[str] = frozenset(
    {"新华网", "新华网时政", "人民网", "人民网时政", "人民日报", "央视新闻", "新华社", "中国日报"}
)
ENGLISH_AUTHORITY: frozenset[str] = frozenset(
    {
        "BBC News",
        "BBC News - World",
        "Reuters",
        "WSJ",
        "NYT",
        "CNN",
        "The Guardian",
        "Bloomberg",
        "Financial Times",
    }
)
MAINSTREAM: frozenset[str] = frozenset(
    {"The Verge", "36氪", "Hacker News", "TechCrunch", "虎嗅", "澎湃新闻", "财新网", "界面新闻"}
)
AUTHORITY: frozenset[str] = CHINESE_AUTHORITY | ENGLISH_AUTHORITY
EVENT_TYPE_LABELS: dict[str, str] = {"breaking": "[突发]", "ongoing": "[进行]", "topic": "[话题]"}


def _calc_source_count_score(news_count: int) -> float:
    """按新闻条数档位计算来源数量子分 (0~1)。"""
    if news_count >= 30:
        return 1.0
    if news_count >= 10:
        return 0.6 + (news_count - 10) / 20 * 0.4
    if news_count >= 5:
        return 0.3 + (news_count - 5) / 4 * 0.3
    return 0.2


def _calc_authority_score(source_names: list[str]) -> float:
    """对事件下全部新闻的 source_name 取平均权威分。"""
    if len(source_names) == 0:
        return 0.0

    def tier(name: str) -> float:
        if name in AUTHORITY:
            return 1.0
        if name in MAINSTREAM:
            return 0.6
        return 0.3

    return sum(tier(n) for n in source_names) / len(source_names)


def _calc_recency_score(last_updated_at: datetime, now: datetime) -> float:
    """根据最后更新时间相对 now 的间隔计算时效子分。"""
    delta: timedelta = now - last_updated_at
    if delta <= timedelta(hours=24):
        return 1.0
    if delta <= timedelta(hours=72):
        return 0.7
    if delta <= timedelta(days=7):
        return 0.4
    return 0.2


def _calc_duration_type(
    first_seen_at: datetime,
    last_updated_at: datetime,
) -> tuple[str, float]:
    """根据首发与末更间隔返回 (event_type, duration 子分)。"""
    duration_days = (last_updated_at - first_seen_at).total_seconds() / 86400.0
    if duration_days < 1:
        return ("breaking", 1.0)
    if duration_days <= 7:
        return ("ongoing", 0.7)
    return ("topic", 0.4)


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
    """event_type 英文字段转终端中文标签。"""
    if event_type is None:
        return "[?]"
    return EVENT_TYPE_LABELS.get(event_type, f"[{event_type}]")


def _truncate_title(title: str, max_len: int = 30) -> str:
    """标题截断用于表格列宽。"""
    stripped = title.strip()
    if len(stripped) <= max_len:
        return stripped
    return stripped[: max_len - 3] + "..."


def print_top_events(events: list[Event]) -> None:
    """打印 Top N 事件表格 (人类可读)。"""
    sep = "═" * 55
    factor_keys = ("source_count", "authority", "recency", "duration")
    print(sep)
    print("Top 15 事件 (按影响力排序)")
    print(sep)
    for idx, event in enumerate(events, start=1):
        score = float(event.impact_score) if event.impact_score is not None else 0.0
        stars = _stars_for_score(score)
        label = _event_type_label(event.event_type)
        title_short = _truncate_title(event.title)
        print(
            f"#{idx}  {stars} {label} {score:.4f}  "
            f"{title_short:<30}  {event.news_count} 条"
        )
        raw = event.impact_factors
        if isinstance(raw, dict):
            parts: list[str] = []
            for key in factor_keys:
                val = raw.get(key)
                if isinstance(val, (int, float)):
                    parts.append(f"{key}={float(val):.3f}")
                else:
                    parts.append(f"{key}=-")
            print("     " + " | ".join(parts))
        else:
            print("     (无 impact_factors)")
    print(sep)
    print(f"共展示 {len(events)} 条 (库内已评分事件可能少于 15)")
    print(sep)


async def fetch_source_names_for_event(session: AsyncSession, event_id: uuid.UUID) -> list[str]:
    """JOIN event_news 取某事件下全部新闻的 source_name (一行一条新闻)。"""
    stmt = (
        select(News.source_name)
        .join(EventNews, EventNews.news_id == News.id)
        .where(EventNews.event_id == event_id)
    )
    result = await session.execute(stmt)
    return [str(row[0]) for row in result.all()]


async def main() -> int:
    """执行影响力评分主流程, 返回进程退出码 (0 成功, 1 提交失败)。"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Event).order_by(Event.news_count.desc()))
        events: list[Event] = list(result.scalars().all())

        if len(events) == 0:
            logger.info("score_no_events", message="events 表为空")
            return 0

        now = datetime.now(timezone.utc)
        scored_count = 0
        skipped_no_news = 0

        for event in events:
            source_names = await fetch_source_names_for_event(session, event.id)

            if len(source_names) == 0:
                logger.warning(
                    "score_event_no_news",
                    event_id=str(event.id),
                    message="事件无关联新闻, 跳过",
                )
                skipped_no_news += 1
                continue

            if event.news_count != len(source_names):
                logger.warning(
                    "score_event_count_mismatch",
                    event_id=str(event.id),
                    news_count_field=event.news_count,
                    actual_join_count=len(source_names),
                    message="事件 news_count 与 JOIN 得到的来源数不一致, 数据完整性提示",
                )

            source_count_score = _calc_source_count_score(event.news_count)
            authority_score = _calc_authority_score(source_names)
            recency_score = _calc_recency_score(event.last_updated_at, now)
            event_type, duration_score = _calc_duration_type(
                event.first_seen_at,
                event.last_updated_at,
            )

            impact_score = (
                0.4 * source_count_score
                + 0.3 * authority_score
                + 0.2 * recency_score
                + 0.1 * duration_score
            )

            event.impact_score = round(impact_score, 4)
            event.event_type = event_type
            event.impact_factors = {
                "source_count": round(source_count_score, 3),
                "authority": round(authority_score, 3),
                "recency": round(recency_score, 3),
                "duration": round(duration_score, 3),
            }
            scored_count += 1

        try:
            await session.commit()
        except Exception as exc:  # noqa: BLE001 - commit 失败需 rollback 后退出
            await session.rollback()
            logger.error(
                "score_commit_failed",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return 1

        logger.info(
            "score_completed",
            total_events=len(events),
            scored_count=scored_count,
            skipped_no_news=skipped_no_news,
        )

        top_result = await session.execute(
            select(Event)
            .where(Event.impact_score.is_not(None))
            .order_by(Event.impact_score.desc())
            .limit(15)
        )
        top_events: list[Event] = list(top_result.scalars().all())
        print_top_events(top_events)

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
