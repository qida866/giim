"""持久化源健康，保留最后成功/失败，失败不等于没有新闻。"""

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.operations import OperationalState
from src.ingestion.orchestrator_schema import SourceRunStats


def health_value(old: dict, result: SourceRunStats, now: datetime) -> dict:
    value = result.model_dump(mode="json")
    value["last_checked"] = now.isoformat()
    value["last_success"] = now.isoformat() if result.success else old.get("last_success")
    value["last_failure"] = old.get("last_failure") if result.success else now.isoformat()
    value["last_error"] = (
        old.get("last_error") if result.success else result.fetch_error or result.insert_error
    )
    value["consecutive_failures"] = 0 if result.success else old.get("consecutive_failures", 0) + 1
    for key in ("latest_published_at", "etag", "last_modified"):
        if value.get(key) is None and (key == "latest_published_at" or old.get("fetch_url", "") == result.fetch_url):
            value[key] = old.get(key)
    history = old.get("history", [])[-19:]
    value["history"] = history + [
        {
            "at": now.isoformat(),
            "success": result.success,
            "inserted": result.inserted,
            "updated": result.updated,
            "duration_ms": round(result.duration_ms, 1),
            "not_modified": result.not_modified,
        }
    ]
    return value


async def save_source_health(session: AsyncSession, results: list[SourceRunStats]) -> None:
    now = datetime.now(timezone.utc)
    for result in results:
        key = "source:" + (result.source_id or result.source_name)
        state = await session.get(OperationalState, key)
        value = health_value(state.value if state else {}, result, now)
        if state:
            state.value = value
        else:
            session.add(OperationalState(key=key, value=value))
    await session.commit()
