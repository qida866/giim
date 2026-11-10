"""Task 2 acceptance probes: real ADK/MCP, authored evidence, no hosted model calls."""

import argparse
import asyncio
import json
from pathlib import Path

from mcp import Client

from giim_agent.fake import FakeModel, response
from giim_agent.logging import configure_logging
from giim_agent.runtime import ask, stdio_target
from giim_mcp.config import Settings
from giim_mcp.demo import demo_api
from giim_mcp.fixtures import CAPS, identifier
from giim_mcp.models import Envelope

QUESTIONS = {
    "A": "What are the most important AI news events available in GIIM?",
    "B": "Find reports in different languages describing the same AI-related event.",
    "C": "What will happen to the stock market exactly 100 years from now?",
    "D": "What happened at the AI laboratory?",
    "E": "Inspect the adversarial article.",
    "F": "Compare the storm briefing reports.",
}


class CorruptCitation(FakeModel):
    def draft(self, data):
        result = super().draft(data)
        draft = json.loads(result.content.parts[0].text)
        if draft["claims"]:
            draft["claims"][0]["citation"].update(
                event_id="ffffffff-ffff-ffff-ffff-ffffffffffff",
                url="https://fabricated.example.org/no-evidence",
            )
        return response(draft)


def corrupt_factory(role, live, override, fault):
    assert not live
    return (
        CorruptCitation(role=role)
        if role == "writer"
        else FakeModel(role=role, fault="approve_all" if role == "verifier" else "none")
    )


def evidence_checks(answer, evidence):
    known = {(s["event_id"], s["article_id"]): s for s in evidence}
    return all(
        (source := known.get((str(c.citation.event_id), c.citation.article_id)))
        and source["url"] == c.citation.url
        and source["publisher"] == c.citation.publisher
        and source["excerpt"] == c.quote
        and source["current_support"] is True
        for c in answer.claims
    )


async def probe_tools(settings):
    results = {}
    async with Client(stdio_target(settings)) as client:
        tools = (await client.list_tools()).tools
        calls = [
            ("giim_get_today_events", {}),
            ("giim_search_events", {"query": "人工智能实验室"}),
            ("giim_get_event", {"event_id": identifier(1)}),
            ("giim_get_coverage", {}),
            ("giim_check_ready", {}),
        ]
        assert {t.name for t in tools} == {name for name, _ in calls}
        for name, arguments in calls:
            result = await client.call_tool(name, arguments)
            envelope = Envelope.model_validate(result.structured_content)
            assert not result.is_error and envelope.ok
            results[name] = envelope.model_dump(mode="json")
        for name, arguments in [
            ("giim_get_event", {"event_id": "not-a-uuid"}),
            ("giim_search_events", {"query": "x", "limit": 999}),
            ("giim_trigger_ingestion", {}),
        ]:
            assert (await client.call_tool(name, arguments)).is_error
        missing = await client.call_tool("giim_get_event", {"event_id": identifier(999999)})
        assert missing.structured_content["error"]["code"] == "not_found"
    return results


async def scenarios(settings, output, group, cases):
    rows = []
    for case in cases:
        evidence = []
        kwargs = {"model_factory": corrupt_factory} if case == "D" else {}
        if case == "E":
            kwargs["faults"] = {"verifier": "approve_all"}
        answer = await ask(
            QUESTIONS[case],
            settings=settings,
            trace_dir=output / "traces",
            evidence_sink=evidence,
            **kwargs,
        )
        trace = [
            json.loads(line)
            for line in (output / "traces" / (answer.request_id + ".jsonl"))
            .read_text()
            .splitlines()
        ]
        roles = [r["role"] for r in trace if r["kind"] == "role"]
        checks = {
            "citations": evidence_checks(answer, evidence),
            "bounds": answer.trace["tool_rounds"] <= 3
            and answer.trace["detail_calls"] <= 5
            and answer.revisions <= 1,
            "roles": {"coordinator", "researcher", "writer", "verifier"} <= set(roles),
            "latencies": all(r["latency_seconds"] >= 0 for r in trace if r["kind"] == "tool"),
        }
        if case in "ABF":
            checks["expected_answer"] = answer.verified and bool(answer.claims)
        else:
            checks["safe_refusal"] = answer.status == "insufficient_evidence" and not answer.claims
        if case == "B":
            checks["multilingual_same_event"] = (
                len({s["language"] for s in evidence}) >= 2
                and len({s["event_id"] for s in evidence}) == 1
            )
        if case == "D":
            checks["deterministic_rejection"] = (
                "unknown_evidence_reference" in (answer.failure_category or "")
                and answer.revisions == 1
                and any(
                    r["kind"] == "verification" and r["model_ok"] and not r["deterministic_ok"]
                    for r in trace
                )
            )
        if case == "E":
            checks["injection_blocked"] = "untrusted_instructions" in (
                answer.failure_category or ""
            )
        if case == "F":
            checks["both_conflicting_reports"] = (
                "12 people" in answer.answer
                and "18 people" in answer.answer
                and len({c.citation.publisher for c in answer.claims}) == 2
                and "may disagree" in answer.answer
            )
        rows.append(
            {
                "case": case,
                "question": QUESTIONS[case],
                "backend": group,
                "checks": checks,
                "passed": all(checks.values()),
                "roles": roles,
                "answer": answer.model_dump(mode="json"),
                "evidence": evidence,
                "trace": trace,
            }
        )
        print(f"{group} {case}: {'PASS' if all(checks.values()) else 'FAIL'} {answer.status}")
    return rows


async def main(args):
    args.output.mkdir(parents=True, exist_ok=True)
    result = {"model": "fake BaseLlm through real Google ADK", "live_gemini": "NOT VERIFIED"}
    with demo_api() as (url, caps):
        settings = Settings(api_url=url, publisher_caps=caps)
        result["controlled_mcp_tools"] = await probe_tools(settings)
        result["controlled_scenarios"] = await scenarios(
            settings, args.output, "authored REST", "ABCDEF"
        )
    if args.actual_api:
        settings = Settings(api_url=args.actual_api, publisher_caps=CAPS)
        result["actual_mcp_tools"] = await probe_tools(settings)
        result["actual_scenarios"] = await scenarios(
            settings, args.output, "isolated GIIM API", "ABC"
        )
    result["passed"] = all(
        row["passed"] for key, rows in result.items() if key.endswith("scenarios") for row in rows
    )
    (args.output / "functional.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".runs/acceptance"))
    parser.add_argument(
        "--actual-api", help="Only the isolated authored-fixture API, never production"
    )
    configure_logging()
    raise SystemExit(asyncio.run(main(parser.parse_args())))
