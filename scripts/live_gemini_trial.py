"""Approval-gated Gemini trials; --preflight makes no model calls."""

import argparse
import asyncio
import json
import math
import os
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path
from uuid import UUID

from google.adk.models.base_llm import BaseLlm
from google.genai import types
from mcp import Client
from pydantic import BaseModel, ConfigDict, SkipValidation

from giim_agent.budget import Limits
from giim_agent.logging import configure_logging
from giim_agent.roles import make_model
from giim_agent.runtime import ask, stdio_target
from giim_agent.schemas import Draft
from giim_agent.security import SafetyError, environment_secrets, redact
from giim_mcp.config import Settings
from giim_mcp.fixtures import CAPS, RECORDS, identifier
from giim_mcp.models import Detail, Envelope

MODEL = "gemini-3.5-flash-lite"
PRICES = {MODEL: {"input_per_million": 0.30, "output_per_million": 2.50}}
LIMITS = Limits(timeout=180, token_upper_bound=80000)
APPROVAL = "five-workflows-max-50-model-calls-under-1-usd"
RETEST_APPROVAL = "abc-only-max-30-model-calls-under-0.30-usd"


def round_config(name):
    if name == "initial":
        return APPROVAL, 50, 0.95, CASES
    if name == "retest-abc":
        return RETEST_APPROVAL, 30, 0.30, CASES[:3]
    raise SafetyError("trial_unknown_round")


CASES = [
    ("A", "What happened at the synthetic AI laboratory? Find the event and cite its reports."),
    ("B", "查找描述同一人工智能实验室开放事件的不同语言报道，并引用各个来源。"),
    ("C", "What will happen to the stock market exactly 100 years from now?"),
    ("D", "Compare the contradictory attendance reports for the synthetic storm briefing."),
    ("E", "What happened at the synthetic AI laboratory? Verify the source citations."),
]
FIXTURES = [RECORDS[0], RECORDS[3]]
BAD_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
BAD_URL = "https://fabricated.example.org/no-evidence"


def private_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(redact(value, environment_secrets()), stream, ensure_ascii=False, indent=2)
        stream.write("\n")


@dataclass
class Meter:
    max_calls: int = 50
    max_usd: float = 0.95
    calls: int = 0
    reserved_usd: float = 0
    observed_usd: float = 0
    observations: list = field(default_factory=list)

    @property
    def estimated_usd(self):
        # A failed/timeout attempt may be billed without returning usage.
        return self.observed_usd if len(self.observations) == self.calls else None

    def reserve(self, request):
        def schema(value):
            if isinstance(value, type) and issubclass(value, BaseModel):
                return value.model_json_schema()
            return str(value)

        size = len(json.dumps(request.model_dump(exclude_none=True), default=schema).encode())
        # Byte count is a conservative text-token proxy, plus provider/schema margin.
        reservation = ((size + 1000) * 0.30 + 2048 * 2.50) / 1_000_000
        if (
            self.calls >= self.max_calls
            or max(self.reserved_usd, self.observed_usd) + reservation >= self.max_usd
        ):
            raise SafetyError("trial_budget")
        self.calls += 1
        self.reserved_usd += reservation

    def observe(self, response, role):
        usage = response.usage_metadata
        if (
            usage is None
            or usage.prompt_token_count is None
            or usage.candidates_token_count is None
        ):
            raise SafetyError("trial_missing_usage")
        outgoing = usage.candidates_token_count + (usage.thoughts_token_count or 0)
        cost = (usage.prompt_token_count * 0.30 + outgoing * 2.50) / 1_000_000
        self.observed_usd += cost
        self.observations.append({"role": role, "estimated_cost_usd": cost})
        if outgoing > 2048 or self.observed_usd > self.reserved_usd:
            raise SafetyError("trial_usage_exceeded_reservation")


def corrupt_draft(response):
    """Alter a real Writer draft, preserving provider usage and response form."""
    for part in response.content.parts if response.content else []:
        terminal = part.function_call and part.function_call.name == "set_model_response"
        raw = part.function_call.args if terminal else json.loads(part.text) if part.text else None
        if raw is None:
            continue
        draft = Draft.model_validate(raw)
        if not draft.claims:
            continue
        draft.claims[0].citation.event_id = UUID(BAD_ID)
        draft.claims[0].citation.url = BAD_URL
        data = draft.model_dump(mode="json")
        if terminal:
            part.function_call.args = data
        else:
            part.text = json.dumps(data)
        return True
    return False


class TrialModel(BaseLlm):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    delegate: BaseLlm
    role: str
    meter: Meter
    corrupt: bool = False
    records: SkipValidation[list]

    async def generate_content_async(self, llm_request, stream=False):
        if stream:
            raise SafetyError("trial_streaming_disabled")
        llm_request.config.http_options = types.HttpOptions(
            timeout=20000, retry_options=types.HttpRetryOptions(attempts=1)
        )
        llm_request.config.max_output_tokens = 2048
        llm_request.config.candidate_count = 1
        self.meter.reserve(llm_request)
        try:
            async for response in self.delegate.generate_content_async(llm_request, stream=False):
                self.meter.observe(response, self.role)
                if self.corrupt and self.role == "writer":
                    self.records.append({"injected": corrupt_draft(response)})
                # Full role payloads remain private, redacted at write time. No chain-of-thought requested.
                self.records.append(
                    {"role": self.role, "response": response.model_dump(mode="json")}
                )
                yield response
        except Exception as exc:
            diagnostic = {"role": self.role, "exception_type": type(exc).__name__}
            code = getattr(exc, "code", None)
            if isinstance(code, int):
                diagnostic["http_status"] = code
                message = str(exc).lower()
                # Fixed booleans aid diagnosis without copying provider message text.
                diagnostic["mentions_schema"] = "schema" in message
                diagnostic["mentions_format"] = "format" in message
                diagnostic["mentions_additional_properties"] = "additional" in message
            # Exception messages/inputs may contain credentials or request text.
            self.records.append(diagnostic)
            raise


def factory(meter, records, corrupt=False):
    def build(role, live, override, fault):
        if not live or fault != "none":
            raise SafetyError("trial_requires_real_gemini")
        delegate = make_model(role, True, MODEL)
        if delegate.model != MODEL:
            raise SafetyError("trial_model_override")
        delegate.retry_options = types.HttpRetryOptions(attempts=1)
        return TrialModel(
            model=MODEL, delegate=delegate, role=role, meter=meter, corrupt=corrupt, records=records
        )

    return build


async def preflight(settings):
    observations = {}
    async with Client(stdio_target(settings)) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
        expected = {
            "giim_get_today_events",
            "giim_search_events",
            "giim_get_event",
            "giim_get_coverage",
            "giim_check_ready",
        }
        if names != expected:
            raise SafetyError("trial_tool_contract")
        calls = [
            ("giim_get_today_events", {"window": "7d", "limit": 25}),
            ("giim_search_events", {"query": "人工智能实验室", "limit": 20}),
            ("giim_get_coverage", {}),
            ("giim_check_ready", {}),
        ]
        for name, args in calls:
            result = await client.call_tool(name, args)
            env = Envelope.model_validate(result.structured_content)
            if result.is_error or not env.ok:
                raise SafetyError("trial_api_not_ready")
            observations[name] = env.model_dump(mode="json")
        allowed = {row["event"]["id"] for row in FIXTURES}
        for name in ("giim_get_today_events", "giim_search_events"):
            ids = {row["id"] for row in observations[name]["data"]["events"]}
            if ids != allowed:
                raise SafetyError("trial_requires_exact_authored_dataset")
        for row in FIXTURES:
            result = await client.call_tool("giim_get_event", {"event_id": row["event"]["id"]})
            env = Envelope.model_validate(result.structured_content)
            if result.is_error or not env.ok:
                raise SafetyError("trial_missing_authored_event")
            detail = Detail.model_validate(env.data)
            actual = {
                (s.article_id, s.publisher, s.url, s.excerpt, s.language)
                for s in detail.articles
                if s.current_support
            }
            expected_sources = {
                (s["id"], s["source"], s["url"], s["excerpt"], s["language"])
                for s in row["articles"]
            }
            if actual != expected_sources or detail.total_articles != len(expected_sources):
                raise SafetyError("trial_unreviewed_source_content")
            observations[row["event"]["id"]] = env.model_dump(mode="json")
    return observations


def checks(case, answer, evidence, events, records):
    known = {(s["event_id"], s["article_id"]): s for s in evidence}
    result = {
        "all_roles": {"coordinator", "researcher", "writer", "verifier"}
        <= {e["role"] for e in events if e["kind"] == "role"},
        "real_model_usage": bool(answer.trace.get("model_calls"))
        and answer.trace.get("estimated_cost_usd") is not None,
        "citations": all(
            (s := known.get((str(c.citation.event_id), c.citation.article_id)))
            and s["excerpt"] == c.quote
            and s["url"] == c.citation.url
            and s["publisher"] == c.citation.publisher
            for c in answer.claims
        ),
    }
    result["complete_model_usage"] = sum(e["kind"] == "model_start" for e in events) == sum(
        e["kind"] == "model" for e in events
    )
    result["verification_executed"] = any(e["kind"] == "verification" for e in events)
    if case in "ABD":
        result["mcp_retrieval"] = {"giim_search_events", "giim_get_event"} <= {
            e["tool"] for e in events if e["kind"] == "tool"
        }
        result["both_verifiers_approved"] = any(
            e["kind"] == "verification" and e["model_ok"] and e["deterministic_ok"] for e in events
        )
        target = identifier(4 if case == "D" else 1)
        result["relevant_verified_answer"] = (
            answer.verified
            and bool(answer.claims)
            and all(str(c.citation.event_id) == target for c in answer.claims)
        )
    else:
        result["refusal"] = not answer.claims and answer.status == "insufficient_evidence"
    if case == "B":
        result["languages"] = (
            len(
                {
                    known[(str(c.citation.event_id), c.citation.article_id)]["language"]
                    for c in answer.claims
                }
            )
            >= 2
        )
    if case == "D":
        result["conflicting_reports_preserved"] = (
            "12 people" in answer.answer and "18 people" in answer.answer
        )
        result["researcher_detected_conflict"] = any(
            '"contradictions": true' in json.dumps(r).replace('\\"', '"')
            for r in records
            if r.get("role") == "researcher"
        )
    if case == "E":
        result["injection_exercised"] = any(r.get("injected") for r in records)
        result["gate_rejected"] = any(
            e["kind"] == "verification"
            and not e["deterministic_ok"]
            and "unknown_evidence_reference" in e["errors"]
            for e in events
        )
        result["verifier_rejected"] = any(
            e["kind"] == "verification" and not e["model_ok"] for e in events
        )
    return result


def resume_state(path, carry_unreported=False, round_name="initial"):
    """Continue only unattempted scenarios, carrying all prior spending forward."""
    _, max_calls, max_usd, cases = round_config(round_name)
    if path is None:
        return Meter(max_calls=max_calls, max_usd=max_usd), []
    data = json.loads(path.read_text())
    calls, reserved, measured = (
        data["attempted_model_calls"],
        data["reserved_usd"],
        data["observed_estimated_usd"],
    )
    missing_usage = measured is None
    if missing_usage and carry_unreported:
        measured = data.get("known_response_estimate_usd")
    if (
        data.get("round", "initial") != round_name
        or data["model"] != MODEL
        or isinstance(calls, bool)
        or not isinstance(calls, int)
        or not 0 <= calls <= max_calls
        or measured is None
        or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
            for v in (reserved, measured)
        )
        or max(reserved, measured) >= max_usd
    ):
        raise SafetyError("trial_invalid_or_exhausted_resume_budget")
    completed = [r for r in data["results"] if "answer" in r]
    identifiers = [r["case"] for r in completed]
    if len(identifiers) != len(set(identifiers)) or identifiers != [
        c for c, _ in cases[: len(completed)]
    ]:
        raise SafetyError("trial_invalid_resume_cases")
    returned = sum(r["answer"]["trace"]["model_calls"] for r in completed)
    if returned > calls or (returned != calls and not (carry_unreported and missing_usage)):
        raise SafetyError("trial_incomplete_resume_usage")
    return Meter(
        max_calls=max_calls,
        max_usd=max_usd,
        calls=calls,
        reserved_usd=reserved,
        observed_usd=measured,
        observations=[{} for _ in range(returned)],
    ), completed


async def run(args):
    round_name = getattr(args, "round", "initial")
    approval, _, _, cases = round_config(round_name)
    if args.live and os.getenv("GIIM_LIVE_TRIAL_APPROVAL") == approval:
        credential = getattr(args, "credential_file", None)
        if credential:
            os.environ["GOOGLE_API_KEY"] = credential.read_text().strip()
    if args.live and (
        os.getenv("GIIM_LIVE_TRIAL_APPROVAL") != approval
        or os.getenv("GIIM_ENABLE_LIVE_GEMINI") != "1"
        or not os.getenv("GOOGLE_API_KEY")
    ):
        raise SafetyError("trial_approval_and_private_credential_required")
    if args.api != "http://127.0.0.1:8000":
        raise SafetyError("trial_requires_isolated_container_network")
    meter, results = resume_state(
        getattr(args, "resume_from", None),
        getattr(args, "carry_unreported_reservation", False),
        round_name,
    )
    settings = Settings(api_url=args.api, publisher_caps=CAPS)
    # mkdir is exclusive: rerunning an approved trial cannot silently add more paid work.
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    observations = await preflight(settings)
    private_json(
        args.output / "preflight.json",
        {
            "sdk_versions": {
                p: version(p) for p in ("google-adk", "google-genai", "mcp", "pydantic")
            },
            "observations": observations,
        },
    )
    if not args.live:
        print(
            "PASS: five actual API MCP tools and exact authored two-event dataset; zero model calls."
        )
        return 0
    for case, question in cases[len(results) :]:
        evidence, records = [], []
        answer = await ask(
            question,
            settings=settings,
            live=True,
            model=MODEL,
            limits=LIMITS,
            prices=PRICES,
            trace_dir=args.output / "traces",
            evidence_sink=evidence,
            model_factory=factory(meter, records, case == "E"),
        )
        events = [
            json.loads(line)
            for line in (args.output / "traces" / (answer.request_id + ".jsonl"))
            .read_text()
            .splitlines()
        ]
        verified = checks(case, answer, evidence, events, records)
        failure = answer.failure_category or ""
        blocked = answer.status == "error" or failure.startswith("trial_")
        status = "BLOCKED" if blocked else "PASS" if all(verified.values()) else "FAIL"
        results.append(
            {
                "case": case,
                "question": question,
                "status": status,
                "checks": verified,
                "answer": answer.model_dump(mode="json"),
                "evidence": evidence,
                "role_responses": records,
            }
        )
        private_json(
            args.output / "results.json",
            {
                "model": MODEL,
                "round": round_name,
                "results": results,
                "attempted_model_calls": meter.calls,
                "reserved_usd": meter.reserved_usd,
                "observed_estimated_usd": meter.estimated_usd,
                "known_response_estimate_usd": meter.observed_usd,
                "unreported_model_attempts": meter.calls - len(meter.observations),
            },
        )
        print(f"{case}: {status}; estimated cumulative USD {meter.estimated_usd}")
        if status != "PASS":
            for remaining, text in cases[len(results) :]:
                results.append(
                    {
                        "case": remaining,
                        "question": text,
                        "status": "BLOCKED",
                        "reason": "Stopped after the first failed or blocked scenario; no automatic paid reruns.",
                    }
                )
            private_json(
                args.output / "results.json",
                {
                    "model": MODEL,
                    "round": round_name,
                    "results": results,
                    "attempted_model_calls": meter.calls,
                    "reserved_usd": meter.reserved_usd,
                    "observed_estimated_usd": meter.estimated_usd,
                    "known_response_estimate_usd": meter.observed_usd,
                    "unreported_model_attempts": meter.calls - len(meter.observations),
                },
            )
            return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--credential-file", type=Path)
    parser.add_argument("--round", choices=("initial", "retest-abc"), default="initial")
    parser.add_argument(
        "--carry-unreported-reservation",
        action="store_true",
        help="After investigation, retain full prior reservations for unreported attempts; never treat them as free",
    )
    parser.add_argument(
        "--resume-from", type=Path, help="Previous results; only unattempted workflows may run"
    )
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    configure_logging()
    try:
        raise SystemExit(asyncio.run(run(parser.parse_args())))
    except Exception as exc:
        print("BLOCKED: " + (str(exc) if isinstance(exc, SafetyError) else type(exc).__name__))
        raise SystemExit(2) from None
