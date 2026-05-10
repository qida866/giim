"""命令行入口:跑一次完整采集。

用法:
    docker compose exec api python -m scripts.run_ingestion

注意:实际编排逻辑在 src.ingestion.orchestrator,
本脚本只是命令行包装。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 让 scripts 目录能 import src.xxx
PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.ingestion.orchestrator import run_ingestion


async def main() -> int:
    """跑一次采集,返回 exit code(0=有源成功 1=全部失败)。"""
    stats = await run_ingestion()

    print(
        f"Run finished: {stats.sources_succeeded}/{stats.sources_total} "
        f"sources succeeded, "
        f"inserted={stats.items_inserted_total}, "
        f"duration={stats.total_duration_ms:.1f}ms"
    )

    return 0 if stats.sources_succeeded > 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
