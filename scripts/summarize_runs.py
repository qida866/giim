"""汇总私有 JSONL；先安装独立 giim-agent 开发环境。"""

import argparse
import json
from pathlib import Path

from giim_agent.stats import summarize

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", type=Path, default=Path(".runs"))
    args = parser.parse_args()
    print(json.dumps(summarize(args.directory), indent=2))
