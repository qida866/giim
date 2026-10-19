"""有界、按发布者轮转的发现窗口，防止高频单源挤掉地区报道。"""

from collections import defaultdict, deque
from src.models.news import News
from src.services.evidence_coverage import publisher_id


def balanced_window(news: list[News], limit: int = 1500) -> list[News]:
    buckets = defaultdict(deque)
    for n in sorted(news, key=lambda n: n.published_at, reverse=True):
        buckets[publisher_id(n)].append(n)
    result = []
    while buckets and len(result) < limit:
        for key in list(buckets):
            result.append(buckets[key].popleft())
            if not buckets[key]:
                del buckets[key]
            if len(result) >= limit:
                break
    return result
