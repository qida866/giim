"""基于已完成追踪计算统计；分别报告缺失用量与未完成请求。"""

import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean


def numeric(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def summarize(directory: Path) -> dict:
    requests, complete = set(), {}
    malformed = 0
    starts, returned = Counter(), Counter()
    known_costs = []
    for path in directory.glob("*.jsonl"):
        with path.open() as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    key = row["request_id"]
                    if not isinstance(key, str):
                        raise ValueError("invalid ID")
                    requests.add(key)
                    if row.get("kind") == "model_start":
                        starts[key] += 1
                    elif row.get("kind") == "model":
                        returned[key] += 1
                        if numeric(row.get("estimated_cost_usd")):
                            known_costs.append(row["estimated_cost_usd"])
                    if row.get("kind") == "complete":
                        complete[key] = row
                except (ValueError, TypeError, KeyError):
                    malformed += 1
    missing = {key: starts[key] - returned[key] for key in starts if starts[key] > returned[key]}
    # Older complete events summed successful responses despite later failed attempts.
    # Correct their aggregates without altering historical JSONL evidence.
    for key in missing:
        if key in complete:
            complete[key] = {
                **complete[key],
                **{
                    field: None
                    for field in (
                        "input_tokens",
                        "output_tokens",
                        "total_tokens",
                        "estimated_cost_usd",
                    )
                },
            }
    rows = list(complete.values())

    def values(key):
        return [r[key] for r in rows if numeric(r.get(key))]

    def average(key):
        v = values(key)
        return mean(v) if v else None

    latencies = sorted(values("latency_seconds"))

    def percentile(p):
        return latencies[max(0, math.ceil(p * len(latencies)) - 1)] if latencies else None

    measured = [
        r
        for r in rows
        if numeric(r.get("total_tokens"))
        and numeric(r.get("latency_seconds"))
        and r["latency_seconds"] > 0
    ]
    return {
        "total_requests": len(requests),
        "unreported_model_attempts": sum(missing.values()),
        "known_response_estimate_usd": sum(known_costs) if known_costs else None,
        "total_estimated_cost_usd": sum(values("estimated_cost_usd"))
        if rows and len(values("estimated_cost_usd")) == len(rows)
        else None,
        "completed_requests": len(rows),
        "incomplete_requests": len(requests - set(complete)),
        "malformed_lines": malformed,
        "successful_requests": sum(r.get("status") == "verified" for r in rows),
        "insufficient_evidence_requests": sum(
            r.get("status") == "insufficient_evidence" for r in rows
        ),
        "failed_requests": sum(r.get("status") == "error" for r in rows),
        "mean_tool_calls": average("tool_calls"),
        "mean_estimated_cost_usd": average("estimated_cost_usd"),
        "priced_requests": len(values("estimated_cost_usd")),
        "p50_latency_seconds": percentile(0.5),
        "p95_latency_seconds": percentile(0.95),
        "percentile_method": "nearest rank, completed requests",
        "verification_pass_rate": sum(r.get("verified") is True for r in rows) / len(rows)
        if rows
        else None,
        "mean_revisions": average("revisions"),
        "mean_total_tokens": average("total_tokens"),
        "measured_token_requests": len(values("total_tokens")),
        "tokens_per_second": sum(r["total_tokens"] for r in measured)
        / sum(r["latency_seconds"] for r in measured)
        if measured
        else None,
    }
