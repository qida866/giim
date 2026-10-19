"""保留流水线历史与最后成功/失败，不让单次错误抹去运维背景。"""

from sqlalchemy.ext.asyncio import AsyncSession
from src.models.operations import OperationalState


async def save_pipeline_state(session: AsyncSession, result: dict) -> None:
    state = await session.get(OperationalState, "pipeline")
    if state:
        state.value = result
    else:
        session.add(OperationalState(key="pipeline", value=result))
    history = await session.get(OperationalState, "pipeline_history")
    old = history.value if history else {}
    record = {k: v for k, v in result.items() if k != "stages"}
    stages = result.get("stages", {})
    record["events_published"] = stages.get("events_published", 0)
    record["embedded"] = stages.get("vectors", {}).get("embedded", 0)
    record["llm_calls"] = result.get("llm_usage", {}).get(
        "logical_requests", stages.get("quality", {}).get("llm_calls", 0)
    )
    record["source_failures"] = stages.get("ingestion", {}).get("sources_failed")
    value = {**old, "runs": old.get("runs", [])[-29:] + [record]}
    if result.get("status") in {"success", "no_current_evidence"}:
        value["last_success"] = result.get("finished_at")
    elif result.get("status") == "failed":
        value["last_failure"] = result.get("finished_at")
    if history:
        history.value = value
    else:
        session.add(OperationalState(key="pipeline_history", value=value))
    await session.commit()
