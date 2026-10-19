"""读取注册表别名统一旧发布者名称；不改写历史新闻。"""

from functools import lru_cache
import os
from pathlib import Path
from src.ingestion.registry import load_registry
from src.models.news import News


@lru_cache(maxsize=4)
def _aliases(path: str, modified: int) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for source in load_registry(include_disabled=True):
        for value in (source.name, source.publisher_id):
            aliases[value.strip().casefold()] = source.publisher_id.strip().casefold()
    return aliases


def canonical_name(value: str) -> str:
    normalized = value.strip().casefold()
    path = Path(os.getenv('SOURCE_REGISTRY_PATH', str(Path.cwd() / 'config/sources.json')))
    return _aliases(str(path), path.stat().st_mtime_ns).get(normalized, normalized)


def publisher_id(news: News) -> str:
    value = (news.raw_metadata or {}).get('publisher_id') or news.source_name
    return canonical_name(str(value))
