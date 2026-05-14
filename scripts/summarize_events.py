"""命令行入口:为 summary 为空的事件调用 LLM 生成中文摘要并写回 PostgreSQL。

编排逻辑见 Day 6 C 阶段设计草案 v2。依赖 DEEPSEEK_API_KEY / LLM_BASE_URL / LLM_MODEL 等环境变量。

用法示例:
    docker compose exec api python -m scripts.summarize_events

可选环境变量:
    SUMMARIZE_LIMIT=10
    SUMMARIZE_NEWS_PER_EVENT=5
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# 让 scripts 目录能 import src.xxx
PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.core.logging import get_logger
from src.db.session import AsyncSessionLocal
from src.llm import LLMClient, LLMError
from src.llm.schema import LLMMessage, LLMRequest
from src.models.event import Event, EventNews
from src.models.news import News

logger = get_logger(__name__)

SUMMARIZE_SYSTEM_MESSAGE = (
    "你是一位专业新闻编辑, 擅长将多条同一事件的报道凝练为简洁、客观、3 句话的中文摘要。"
)


def _build_user_prompt(n: int, news_block: str) -> str:
    """拼装 Day 6 C 用户侧完整 prompt (零样本,无 few-shot 示例)。"""
    return (
        f"你是一个新闻分析助手。下面是围绕同一事件的 {n} 条新闻报道"
        f"（按发布时间从新到旧排列）。请阅读全部材料后作答。\n\n"
        f"{news_block}\n\n"
        "请用中文总结这个事件，输出恰好 3 句话，并满足下列结构"
        "（每句单独一行，句末可不用句号以外的多余标点）：\n\n"
        "第 1 句：说明事件本身是什么，尽量包含 Who / What / Where / When 中能从前文推断出的要素。\n"
        "第 2 句：说明当前进展或最新动态（若多条新闻信息重复，请合并为一条连贯表述）。\n"
        "第 3 句：补充背景、动因或可能的影响（仅基于材料，勿臆测不存在的事实）。\n\n"
        "硬性要求：\n"
        "1. 每句不超过 50 个汉字（不含换行）；若材料不足某一句，用合理的概括语言写满一句，"
        "但绝不编造具体数字、人名、机构名；不能确定的细节用「等」、「相关」等概括词。\n"
        "2. 全文客观、中性；不要使用「据报道」「据悉」「有分析认为」等套话。\n"
        "3. 输出为纯文字：不要使用 Markdown、项目符号、编号列表或标题；"
        "仅 3 行正文，行与行之间用换行分隔。\n"
        "4. 不要逐句复述或照抄任一条新闻的标题原文；应概括多条报道的共性信息。\n"
        "5. 不要输出「好的」「以下是摘要」等寒暄或元话语；直接输出 3 句话正文。"
    )


@dataclass(frozen=True)
class SummarizeConfig:
    """摘要脚本可调参数 (来自环境变量)。"""
    limit: int | None
    news_per_event: int


def load_summarize_config() -> SummarizeConfig:
    """解析 SUMMARIZE_LIMIT / SUMMARIZE_NEWS_PER_EVENT,非法则抛出 ValueError。"""
    raw_limit = os.getenv("SUMMARIZE_LIMIT")
    if raw_limit is None or raw_limit.strip() == "":
        limit_value: int | None = None
    else:
        try:
            limit_value = int(raw_limit.strip())
        except ValueError as exc:
            raise ValueError(f"SUMMARIZE_LIMIT 非法: {raw_limit!r}") from exc
        if limit_value <= 0:
            raise ValueError(f"SUMMARIZE_LIMIT 必须为正整数,当前为 {limit_value}")

    raw_news = os.getenv("SUMMARIZE_NEWS_PER_EVENT", "5").strip()
    try:
        news_per_event = int(raw_news)
    except ValueError as exc:
        raise ValueError(f"SUMMARIZE_NEWS_PER_EVENT 非法: {raw_news!r}") from exc
    if news_per_event < 1 or news_per_event > 10:
        raise ValueError(f"SUMMARIZE_NEWS_PER_EVENT 须在 1-10 之间,当前为 {news_per_event}")

    return SummarizeConfig(limit=limit_value, news_per_event=news_per_event)


def _format_body_snippet(content: str) -> str:
    """取正文前 500 字并单行化;空正文用占位。"""
    stripped = (content or "").strip()
    if not stripped:
        return "(无正文)"
    snippet = stripped[:500]
    return snippet.replace("\n", " ").replace("\r", " ")


def build_messages(event: Event, rows: list[tuple[str, str]]) -> list[LLMMessage]:
    """构造 system + user 两条消息;event 参数保留供调用方语义一致。"""
    _ = event
    parts: list[str] = []
    for idx, (title, body) in enumerate(rows, start=1):
        parts.append(f"[新闻 {idx}]\n标题: {title}\n内容: {body}")
    news_block = "\n\n".join(parts)
    n = len(rows)
    user_content = _build_user_prompt(n, news_block)
    return [
        LLMMessage(role="system", content=SUMMARIZE_SYSTEM_MESSAGE),
        LLMMessage(role="user", content=user_content),
    ]


async def load_pending_events(session: AsyncSession, limit: int | None) -> list[Event]:
    """查询待生成摘要的事件,按 news_count 降序。"""
    stmt = select(Event).where(Event.summary.is_(None)).order_by(Event.news_count.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def fetch_top_news_for_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    limit: int,
) -> list[tuple[str, str]]:
    """JOIN event_news 取某事件最新 N 条新闻的标题与正文片段。"""
    stmt = (
        select(News.title, News.content)
        .join(EventNews, EventNews.news_id == News.id)
        .where(EventNews.event_id == event_id)
        .order_by(News.published_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    out: list[tuple[str, str]] = []
    for row in result.all():
        title = str(row.title)
        body = _format_body_snippet(str(row.content) if row.content is not None else "")
        out.append((title, body))
    return out


async def main() -> int:
    """执行事件摘要主流程,返回进程退出码 (0 成功,1 失败)。"""
    try:
        cfg = load_summarize_config()
    except ValueError as exc:
        logger.error(
            "summarize_config_invalid",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return 1

    try:
        llm = LLMClient()
    except ValueError as exc:
        logger.error(
            "summarize_llm_client_init_failed",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return 1

    success_count = 0
    failed_count = 0
    skipped_no_news = 0

    async with AsyncSessionLocal() as session:
        events = await load_pending_events(session, cfg.limit)
        total = len(events)
        if total == 0:
            logger.info(
                "summarize_no_work",
                message="没有 summary 为空的事件,跳过",
            )
            return 0

        for idx, event in enumerate(events):
            rows = await fetch_top_news_for_event(session, event.id, cfg.news_per_event)
            if len(rows) == 0:
                logger.warning(
                    "summarize_event_no_news",
                    event_id=str(event.id),
                    message="事件无关联新闻,跳过",
                )
                skipped_no_news += 1
            else:
                messages = build_messages(event, rows)
                try:
                    response = await llm.chat(
                        LLMRequest(
                            messages=messages,
                            temperature=0.3,
                            max_tokens=500,
                        ),
                    )
                    text = (response.content or "").strip()
                    if len(text) < 20:
                        logger.warning(
                            "summarize_event_output_too_short",
                            event_id=str(event.id),
                            output_len=len(text),
                            message="LLM 返回过短,跳过写入",
                        )
                        failed_count += 1
                    else:
                        event.summary = text
                        success_count += 1
                except LLMError as exc:
                    logger.error(
                        "summarize_event_llm_failed",
                        event_id=str(event.id),
                        error_type=exc.error_type.value,
                        error_message=str(exc),
                    )
                    failed_count += 1

            if (idx + 1) % 5 == 0:
                try:
                    await session.commit()
                except Exception as exc:  # noqa: BLE001 - commit 失败需 rollback 后退出
                    await session.rollback()
                    logger.error(
                        "summarize_db_commit_failed",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                        message="批量提交失败",
                    )
                    return 1

        try:
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            logger.error(
                "summarize_db_commit_failed",
                error_type=type(exc).__name__,
                error_message=str(exc),
                message="最终提交失败",
            )
            return 1

    logger.info(
        "summarize_completed",
        success_count=success_count,
        failed_count=failed_count,
        skipped_no_news=skipped_no_news,
        total=total,
        message="事件摘要任务结束",
    )
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
