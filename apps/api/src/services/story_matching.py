"""宽松发现候选，绝不凭向量或实体重叠自动合并。"""

from collections import Counter
from datetime import timedelta
import re
import numpy as np
from src.models.news import News


def tokens(news: list[News]) -> set[str]:
    return set(re.findall(r'[^\W\d_]{4,}', ' '.join(n.title for n in news).casefold()))


def fragment_candidates(
    groups: list[list[News]], vectors: dict[int, list[float]], limit: int = 4
) -> list[tuple[int, int, float]]:
    """七天内近邻及稀有标题词只负责召回；最终身份审核必须覆盖全部成员。"""
    terms = [tokens(g) for g in groups]
    frequency = Counter(t for ts in terms for t in ts)
    matrices = []
    for group in groups:
        values = np.asarray([vectors[n.id] for n in group if n.id in vectors])
        if not len(values):
            matrices.append(None)
            continue
        matrices.append(values / np.maximum(np.linalg.norm(values, axis=1, keepdims=True), 1e-12))
    choices: dict[tuple[int, int], float] = {}
    for i, group in enumerate(groups):
        if matrices[i] is None:
            continue
        neighbors = []
        for j in range(i + 1, len(groups)):
            other = groups[j]
            if matrices[j] is None or len(group) + len(other) > 24:
                continue
            times = [n.published_at for n in group + other]
            if max(times) - min(times) > timedelta(days=7):
                continue
            similarity = float(np.max(matrices[i] @ matrices[j].T))
            rare = {t for t in terms[i] & terms[j] if frequency[t] <= max(3, len(groups) // 20)}
            if similarity >= 0.55 or (similarity >= 0.45 and len(rare) >= 2):
                neighbors.append((j, similarity))
        for j, score in sorted(neighbors, key=lambda x: (-x[1], x[0]))[:limit]:
            choices[i, j] = score
    return [(i, j, s) for (i, j), s in sorted(choices.items(), key=lambda x: (-x[1], x[0]))]
