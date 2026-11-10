"""命令行只展示通过确定性门禁的最终回答。"""

import argparse
import asyncio
import json
from contextlib import nullcontext
from pathlib import Path

from giim_mcp.config import Settings
from giim_mcp.demo import demo_api

from .config import pricing
from .runtime import ask
from .logging import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="GIIM evidence-grounded ADK analyst")
    sub = parser.add_subparsers(dest="command", required=True)
    query = sub.add_parser("ask")
    query.add_argument("question")
    query.add_argument(
        "--demo", action="store_true", help="Authored local REST fixtures and fake ADK models"
    )
    query.add_argument("--live", action="store_true", help="Opt-in live Gemini; may incur charges")
    query.add_argument("--model", help="Configured live Gemini model ID")
    query.add_argument("--json", action="store_true", help="Print a structured final answer")
    query.add_argument("--trace", action="store_true", help="Show the private trace path")
    query.add_argument("--trace-dir", type=Path, default=Path(".runs"))
    args = parser.parse_args()
    if args.demo and args.live:
        parser.error("--demo and --live are mutually exclusive")
    if args.model and not args.live:
        parser.error("--model applies only with --live; fake mode never calls Gemini")
    configure_logging()
    try:
        with demo_api() if args.demo else nullcontext(None) as demo:
            settings = (
                Settings(api_url=demo[0], publisher_caps=demo[1]) if demo else Settings.from_env()
            )
            answer = asyncio.run(
                ask(
                    args.question,
                    settings=settings,
                    live=args.live,
                    model=args.model,
                    trace_dir=args.trace_dir,
                    prices=pricing(),
                )
            )
        if args.json:
            print(answer.model_dump_json(indent=2))
        else:
            print(answer.answer)
            print(f"\nMode: {answer.mode}; status: {answer.status}; verified: {answer.verified}")
            print("Tools: " + ", ".join(answer.trace["tools"]))
            print("Trace summary: " + json.dumps(answer.trace))
        if args.trace:
            import sys

            print(str(args.trace_dir / (answer.request_id + ".jsonl")), file=sys.stderr)
        return 0 if answer.status == "verified" else 2
    except (ValueError, OSError):
        print("Configuration or input error; check documented settings. No request details logged.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
