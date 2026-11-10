"""离线合成评测：验证编排和安全机制，不测量真实模型语义准确率。"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from giim_mcp.config import Settings
from giim_mcp.demo import demo_api
from giim_mcp.fixtures import DATASET_VERSION, identifier

from .runtime import ask
from .logging import configure_logging
from .schemas import Answer


def checks(case: dict, answer: Answer, evidence: list[dict]) -> dict[str, bool]:
    lookup = {(s["event_id"], s["article_id"]): s for s in evidence}
    valid = True
    for claim in answer.claims:
        c = claim.citation
        source = lookup.get((str(c.event_id), c.article_id), {})
        valid &= (
            c.url == source.get("url")
            and c.publisher == source.get("publisher")
            and claim.quote == source.get("excerpt")
            and source.get("current_support") is True
        )
    expected_ids = {identifier(i) for i in case.get("events", [])}
    actual_ids = {str(c.citation.event_id) for c in answer.claims}
    return {
        "expected_status": answer.status == case["expect"],
        "citation_associations": bool(valid),
        "expected_events": expected_ids == actual_ids if "events" in case else True,
        "no_claims_on_refusal": answer.verified or not answer.claims,
        "tool_budget": answer.trace["tool_calls"] <= 9
        and answer.trace["detail_calls"] <= 5
        and answer.trace["tool_rounds"] <= 3,
        "revision_budget": answer.revisions <= 1,
        "failure_category": case.get("failure", "") in (answer.failure_category or ""),
        "structured_output": Answer.model_validate(answer.model_dump()) == answer,
    }


def git_state(root: Path) -> dict:
    provided = os.getenv("GIIM_EVAL_COMMIT", "")
    if re.fullmatch(r"[0-9a-f]{40}", provided):
        dirty = os.getenv("GIIM_EVAL_DIRTY")
        return {
            "commit": provided,
            "dirty_worktree": dirty == "1" if dirty else None,
            "metadata_source": "caller-provided checkout Git state",
        }
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True))
        return {"commit": sha, "dirty_worktree": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty_worktree": None}


async def evaluate(dataset: Path, trace_dir: Path | None = None) -> dict:
    config = yaml.safe_load(dataset.read_text())
    if config["dataset_version"] != DATASET_VERSION or len(config["questions"]) < 20:
        raise ValueError("Dataset version or size does not match the authored fixture contract")
    results = []
    with demo_api() as (url, caps):
        for case in config["questions"]:
            evidence = []
            answer = await ask(
                case["question"],
                settings=Settings(api_url=url, publisher_caps=caps),
                faults=case.get("faults"),
                trace_dir=trace_dir,
                evidence_sink=evidence,
            )
            outcomes = checks(case, answer, evidence)
            results.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "question": case["question"],
                    "faults": case.get("faults", {}),
                    "passed": all(outcomes.values()),
                    "checks": outcomes,
                    "answer": answer.model_dump(mode="json"),
                    "retrieved_evidence": evidence,
                    "human_review": "NOT PERFORMED",
                }
            )
    return {
        "dataset_version": DATASET_VERSION,
        "model": "giim-fake-v1",
        "mode": "fake",
        "date": datetime.now(timezone.utc).isoformat(),
        **git_state(dataset.parent),
        "limitations": "Scripted models and authored keyword-routed REST fixtures; measures protocol, "
        "workflow and deterministic safety, not Gemini quality or bge-m3 recall.",
        "questions": len(results),
        "passed": sum(r["passed"] for r in results),
        "results": results,
    }


def default_dataset() -> Path:
    checkout = Path(__file__).resolve().parents[2] / "evals/questions.yaml"
    return checkout if checkout.exists() else Path(sys.prefix) / "share/giim-agent/questions.yaml"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=default_dataset())
    parser.add_argument("--output", type=Path, default=Path(".runs/evaluation.json"))
    parser.add_argument("--trace-dir", type=Path, default=Path(".runs/eval"))
    args = parser.parse_args()
    configure_logging()
    result = asyncio.run(evaluate(args.dataset, args.trace_dir))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    for row in result["results"]:
        print(
            f"{row['id']:4} {row['category']:15} {'PASS' if row['passed'] else 'FAIL'} "
            f"{row['answer']['status']}"
        )
    print(
        f"{result['passed']}/{result['questions']} deterministic cases; fake model; {args.output}"
    )
    return 0 if result["passed"] == result["questions"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
