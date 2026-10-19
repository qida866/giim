"""只从受信任配置文件读取注册表；没有公共源编辑接口。"""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from src.ingestion.source_schema import RssSource


def load_registry(include_disabled: bool = False) -> list[RssSource]:
    path = Path(
        os.getenv(
            "SOURCE_REGISTRY_PATH", str(Path.cwd() / "config/sources.json")
        )
    )
    sources = [RssSource.model_validate(row) for row in json.loads(path.read_text())["sources"]]
    ids = set()
    for source in sources:
        if not source.source_id or source.source_id in ids:
            raise ValueError("Registry source IDs must be present and unique")
        ids.add(source.source_id)
        url = urlsplit(source.url)
        if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password:
            raise ValueError("Registry URLs must be public HTTP(S) without credentials")
    return [s for s in sources if include_disabled or (s.enabled and (s.production_enabled or os.getenv("APP_ENV", "dev") not in {"prod", "production"}))]
