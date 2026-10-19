"""本机运维入口：查看注册表、持久化源健康及实际覆盖，不触发采集。"""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/api'))
from src.db.session import AsyncSessionLocal, async_engine
from src.services.coverage import source_coverage


async def main() -> None:
    try:
        async with AsyncSessionLocal() as session:
            print(json.dumps(await source_coverage(session,168,admin=True),ensure_ascii=False,indent=2))
    finally: await async_engine.dispose()

if __name__=='__main__':asyncio.run(main())
