"""display 工具函数单元测试 (无数据库)。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.utils.display import duration_str, event_type_label, stars_for_score


def test_stars_for_score() -> None:
    """总分映射为星级字符串 (覆盖各阈值边界)。"""
    assert stars_for_score(0.0) == "★☆☆☆☆"
    assert stars_for_score(0.19) == "★☆☆☆☆"
    assert stars_for_score(0.2) == "★★☆☆☆"
    assert stars_for_score(0.39) == "★★☆☆☆"
    assert stars_for_score(0.4) == "★★★☆☆"
    assert stars_for_score(0.59) == "★★★☆☆"  # 0.6 阈值下方
    assert stars_for_score(0.6) == "★★★★☆"  # 0.6 阈值
    assert stars_for_score(0.65) == "★★★★☆"  # 0.6-0.8 区间
    assert stars_for_score(0.79) == "★★★★☆"
    assert stars_for_score(0.8) == "★★★★★"


def test_event_type_label() -> None:
    """event_type 转中文标签。"""
    assert event_type_label("breaking") == "[突发]"
    assert event_type_label("ongoing") == "[进行]"
    assert event_type_label(None) == "[?]"
    assert event_type_label("custom") == "[custom]"


def test_duration_str() -> None:
    """首发至末更时长描述。"""
    base = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    assert duration_str(base, base + timedelta(hours=2)) == "今天"
    assert duration_str(base, base + timedelta(days=6)) == "6 天"
    assert duration_str(base, base + timedelta(days=10)) == "10 天 (长期话题)"
