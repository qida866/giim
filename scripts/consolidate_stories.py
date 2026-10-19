"""默认只读碎片候选；--apply 在流水线同一互斥锁下限额审核合并。"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from sqlalchemy import text
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api'))
from src.db.session import AsyncSessionLocal, async_engine
from src.llm import LLMClient
from src.vector_store import QdrantVectorStore
from src.services.story_consolidation import consolidate_stories


async def main(apply: bool, budget: int) -> None:
    store, llm = QdrantVectorStore(), None
    try:
        async with async_engine.connect() as connection:
            if not await connection.scalar(text('SELECT pg_try_advisory_lock(73499201)')):
                raise RuntimeError('Pipeline already running')
            try:
                llm = LLMClient() if apply else None
                async with AsyncSessionLocal() as session:
                    result = await consolidate_stories(session, store, llm, budget, apply)
                    result["llm_usage"] = llm.metrics if llm else {}
                    print(json.dumps(result, ensure_ascii=False))
            finally:
                await connection.execute(text('SELECT pg_advisory_unlock(73499201)'))
    finally:
        if llm:
            await llm.close()
        await store.close()
        await async_engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--budget', type=int, default=6)
    args = parser.parse_args()
    asyncio.run(main(args.apply, max(0, args.budget)))
