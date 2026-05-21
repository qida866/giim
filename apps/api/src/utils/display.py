"""事件展示辅助: 星级、类型标签、时长 (CLI 与 API 共用)。"""

from __future__ import annotations

from datetime import datetime, timedelta

EVENT_TYPE_LABELS: dict[str, str] = {
    "breaking": "[突发]",
    "ongoing": "[进行]",
    "topic": "[话题]",
}


def stars_for_score(score: float) -> str:
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


def event_type_label(event_type: str | None) -> str:
    """event_type 英文字段转中文标签 (含方括号)。"""
    if event_type is None:
        return "[?]"
    return EVENT_TYPE_LABELS.get(event_type, f"[{event_type}]")


def duration_str(first_seen_at: datetime, last_updated_at: datetime) -> str:
    """首发至末更的时间跨度中文描述。"""
    diff: timedelta = last_updated_at - first_seen_at
    if diff < timedelta(days=1):
        return "今天"
    if diff < timedelta(days=7):
        return f"{diff.days} 天"
    return f"{diff.days} 天 (长期话题)"
