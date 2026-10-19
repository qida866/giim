"""串行、可重复的事件发布流水线。--once 单次，--interval 调度秒数。"""

from __future__ import annotations
import asyncio
import json
import os
import sys
import time
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from sqlalchemy import select, text
from src.db.session import AsyncSessionLocal, async_engine
from src.models.news import News
from src.models.event import Event
from src.models.operations import OperationalState
from src.ingestion.orchestrator import run_ingestion
from src.embedding import EmbeddingClient
from src.llm import LLMClient
from src.vector_store import QdrantVectorStore
from src.services.vector_sync import reconcile_vectors, audit_vectors
from src.services.event_update import prepare_events, publish_events
from src.services.pipeline_state import save_pipeline_state
from src.services.discovery_window import balanced_window
from src.services.continuity import link_continuations
from src.services.story_state import preserve_stories
from src.services.story_consolidation import consolidate_stories
from src.core.logging import get_logger

logger = get_logger(__name__)


async def run_once(fetch: bool = True) -> dict:
    started = time.monotonic()
    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "stages": {},
    }
    async with async_engine.connect() as lock:
        if not await lock.scalar(text("SELECT pg_try_advisory_lock(73499201)")):
            return {"status": "already_running"}
        store = QdrantVectorStore()
        llm = None
        try:
            if fetch:
                stats = await run_ingestion()
                result["stages"]["ingestion"] = stats.model_dump(mode="json")
            async with AsyncSessionLocal() as session:
                result["stages"]["vectors"] = await reconcile_vectors(
                    session, store, EmbeddingClient()
                )
                news = list(
                    (
                        await session.scalars(
                            select(News)
                            .where(
                                News.time_quality == "verified",
                                News.published_at >= datetime.now(timezone.utc) - timedelta(days=7),
                                News.published_at <= datetime.now(timezone.utc),
                            )
                            .order_by(News.published_at.desc())
                            .limit(5000)
                        )
                    ).all()
                )
                news = balanced_window(news)
                result["stages"]["selected_articles"] = len(news)
                decision_state = await session.get(OperationalState, "quality_decisions")
                existing = list(
                    (
                        await session.scalars(
                            select(Event).where(
                                Event.provenance.is_not(None), Event.status == "active"
                            )
                        )
                    ).all()
                )
                known = {
                    e.provenance["evidence_hash"]: {
                        "title": e.title,
                        "summary": e.summary,
                        "provenance": e.provenance,
                    }
                    for e in existing
                    if e.provenance.get("evidence_hash")
                }
                client = await store._get_client()
                points = (
                    await client.retrieve(
                        store._collection_name, ids=[n.id for n in news], with_vectors=True
                    )
                    if news
                    else []
                )
                by_id = {p.id: p.vector for p in points}
                if any(n.id not in by_id for n in news):
                    raise ValueError("Missing vectors after reconciliation")
                try:
                    llm = LLMClient()
                except ValueError:
                    logger.warning("pipeline_llm_unavailable_source_fallback")
                budget = int(os.getenv("PIPELINE_MAX_LLM_CALLS", "20"))
                revalidation = {}
                unclaimed, preserved = await preserve_stories(
                    session, existing, news, llm, min(40, max(4, budget // 4), budget), revalidation)
                result["stages"]["revalidation"] = revalidation
                prepared, quality = await prepare_events(
                    news,
                    [by_id[n.id] for n in news],
                    llm,
                    known,
                    max_calls=max(0, budget - 9 - revalidation.get("revalidation_calls_reserved", 0)),
                    decisions=decision_state.value if decision_state else {},
                    excluded_ids={n.id for n in news} - {n.id for n in unclaimed},
                )
                prepared.extend(preserved)
                decisions = quality.pop("decisions", {})
                if decision_state:
                    decision_state.value = decisions
                else:
                    session.add(OperationalState(key="quality_decisions", value=decisions))
                result["stages"]["quality"] = quality
                result["llm_usage"] = getattr(llm, "metrics", {})
                result["stages"]["continuity"] = await link_continuations(
                    session,
                    prepared,
                    store,
                    llm,
                    max_calls=min(
                        3,
                        max(
                            0, budget - quality["llm_calls"] - revalidation.get("revalidation_calls_reserved", 0)
                        ),
                    ),
                )
                result["stages"]["events_published"] = await publish_events(session, prepared)
                remaining = budget - quality["llm_calls"] - revalidation.get("revalidation_calls_reserved", 0) - result["stages"]["continuity"]["calls"]
                result["stages"]["consolidation"] = await consolidate_stories(session, store, llm, max(0, remaining))
                result["llm_usage"] = getattr(llm, "metrics", {})
                audit, _ = await audit_vectors(session, store)
                result["stages"]["vector_consistency"] = {
                    k: v for k, v in audit.items() if k != "historical_unversioned"
                }
                result["status"] = "success" if news or preserved else "no_current_evidence"
        except Exception as exc:
            result.update(status="failed", error_type=type(exc).__name__)
            logger.exception("pipeline_failed", error_type=type(exc).__name__)
        finally:
            if llm:
                await llm.close()
            await store.close()
            result["duration_seconds"] = round(time.monotonic() - started, 2)
            result["finished_at"] = datetime.now(timezone.utc).isoformat()
            try:
                async with AsyncSessionLocal() as session:
                    await save_pipeline_state(session, result)
            finally:
                await lock.execute(text("SELECT pg_advisory_unlock(73499201)"))
            logger.info(
                "pipeline_finished", status=result["status"], duration=result["duration_seconds"]
            )
    return result


async def main(interval: int, fetch: bool) -> int:
    try:
        while True:
            try:
                result = await run_once(fetch)
            except Exception as exc:
                result = {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "stage": "connection_or_cleanup",
                }
                logger.error("pipeline_unavailable", **result)
            print(json.dumps(result, ensure_ascii=False))
            if not interval:
                return 1 if result["status"] == "failed" else 0
            await asyncio.sleep(interval)
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    p.add_argument("--interval", type=int, default=0)
    p.add_argument("--no-fetch", action="store_true")
    args = p.parse_args()
    if args.interval and args.interval < 300:
        p.error("interval must be at least 300 seconds")
    sys.exit(asyncio.run(main(0 if args.once else args.interval, not args.no_fetch)))
