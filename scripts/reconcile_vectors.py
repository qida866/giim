"""向量对账，默认只读；--repair 仅修复缺失/陈旧的可信新闻。"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from src.db.session import AsyncSessionLocal, async_engine
from src.vector_store import QdrantVectorStore
from src.embedding import EmbeddingClient
from src.services.vector_sync import audit_vectors, reconcile_vectors


async def main(repair: bool = False) -> None:
    store = QdrantVectorStore()
    try:
        async with AsyncSessionLocal() as session:
            result = (
                await reconcile_vectors(session, store, EmbeddingClient())
                if repair
                else (await audit_vectors(session, store))[0]
            )
            print(json.dumps(result, ensure_ascii=False))
    finally:
        await store.close()
        await async_engine.dispose()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--repair", action="store_true")
    asyncio.run(main(p.parse_args().repair))
