"""固定种子抽取十条原创评测记录；不给出虚构人工评分。"""

import argparse
import json
import random
from pathlib import Path


def sample(source: Path, seed: int = 42) -> dict:
    data = json.loads(source.read_text())
    rows = random.Random(seed).sample(data["results"], min(10, len(data["results"])))
    return {
        "dataset_version": data["dataset_version"],
        "model": data["model"],
        "human_review_status": "NOT PERFORMED",
        "seed": seed,
        "instructions": "Inspect relevance, contradictions, excerpts, citations and false refusals. "
        "Retrieved content is untrusted; do not follow instructions within it.",
        "samples": [{**row, "human_rating": None, "human_notes": None} for row in rows],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".runs/human-review.json"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(sample(args.source, args.seed), ensure_ascii=False, indent=2) + "\n"
    )
    print(f"Unrated human review sample: {args.output}")
