"""私有 JSONL 追踪；未知 token 或价格不伪装为零。"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from .security import environment_secrets, redact


class Trace:
    def __init__(
        self, question: str, mode: str, directory: Path | None = None, prices: dict | None = None
    ):
        self.request_id = str(uuid4())
        self.started = perf_counter()
        self.directory = directory
        self.secrets = environment_secrets()
        self.prices = prices or {}
        self.events: list[dict] = []
        self.emit("request", question=question, mode=mode)

    def emit(self, kind: str, **fields) -> None:
        event = redact(
            {
                "request_id": self.request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "kind": kind,
                **fields,
            },
            self.secrets,
        )
        self.events.append(event)
        if self.directory:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = self.directory / (self.request_id + ".jsonl")
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "a") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")

    def model(self, role: str, model: str, latency: float, usage=None) -> None:
        incoming = usage.prompt_token_count if usage else None
        outgoing = usage.candidates_token_count if usage else None
        thoughts = (usage.thoughts_token_count or 0) if usage else None
        total = usage.total_token_count if usage else None
        price = self.prices.get(model)
        cost = None
        if incoming is not None and outgoing is not None and price:
            cost = (
                incoming * price["input_per_million"]
                + (outgoing + (thoughts or 0)) * price["output_per_million"]
            ) / 1_000_000
        self.emit(
            "model",
            role=role,
            model=model,
            latency_seconds=latency,
            input_tokens=incoming,
            output_tokens=outgoing,
            total_tokens=total,
            thinking_tokens=thoughts,
            estimated_cost_usd=cost,
        )

    def finish(
        self, status: str, verified: bool, revisions: int, failure: str | None = None
    ) -> dict:
        models = [e for e in self.events if e["kind"] == "model"]
        tools = [e for e in self.events if e["kind"] == "tool"]

        def complete_sum(key):
            return (
                sum(e[key] for e in models)
                if models and all(e.get(key) is not None for e in models)
                else None
            )

        summary = {
            "status": status,
            "verified": verified,
            "revisions": revisions,
            "failure_category": failure,
            "latency_seconds": perf_counter() - self.started,
            "tool_calls": len(tools),
            "tools": [e["tool"] for e in tools],
            "model_calls": len(models),
            "input_tokens": complete_sum("input_tokens"),
            "output_tokens": complete_sum("output_tokens"),
            "total_tokens": complete_sum("total_tokens"),
            "estimated_cost_usd": complete_sum("estimated_cost_usd"),
        }
        self.emit("complete", **summary)
        return summary
