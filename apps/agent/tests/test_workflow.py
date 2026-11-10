"""真实 ADK Runner、独立角色、stdio MCP 和受控 REST 的端到端测试。"""

import asyncio
import json

import pytest

from giim_agent.runtime import ask
from giim_agent.budget import Limits


async def test_full_workflow_and_traces(settings, tmp_path):
    result = await ask("What happened at the AI laboratory?", settings=settings, trace_dir=tmp_path)
    assert result.verified and len(result.claims) == 3 and result.revisions == 0
    assert result.trace["tools"] == ["giim_search_events", "giim_get_event"]
    assert result.trace["model_calls"] == 5
    assert result.trace["total_tokens"] is None and result.trace["estimated_cost_usd"] is None
    records = [
        json.loads(line)
        for line in (tmp_path / (result.request_id + ".jsonl")).read_text().splitlines()
    ]
    assert {r["role"] for r in records if r["kind"] == "role"} == {
        "coordinator",
        "researcher",
        "writer",
        "verifier",
    }
    assert records[-2]["kind"] != "failure"
    assert any(r["kind"] == "verification" and r["deterministic_ok"] for r in records)
    assert all("excerpt" not in r for r in records)
    assert (tmp_path / (result.request_id + ".jsonl")).stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "question,count",
    [
        ("人工智能实验室有哪些新消息？", 3),
        ("¿Qué ocurrió en el laboratorio?", 3),
        ("Que rapporte le télescope orbital ?", 2),
    ],
)
async def test_multilingual_controlled_routing(settings, question, count):
    result = await ask(question, settings=settings, trace_dir=None)
    assert result.verified and len(result.claims) == count


async def test_evolving_event_current_support_only(settings):
    result = await ask("Did the bridge reopen after the flood?", settings=settings, trace_dir=None)
    assert result.verified
    assert all(
        "remained closed" not in c.quote and not c.citation.url.endswith("old")
        for c in result.claims
    )
    assert "reopened" in result.answer


async def test_conflict_preserved(settings):
    result = await ask(
        "Compare the storm briefing attendance reports.", settings=settings, trace_dir=None
    )
    assert result.verified and len(result.claims) == 2
    assert "12 people" in result.answer and "18 people" in result.answer
    assert "may disagree" in result.answer


@pytest.mark.parametrize(
    "fault",
    ["bad_url", "bad_event", "bad_article", "unsupported", "omit_conflict", "omit_uncertainty"],
)
async def test_deterministic_gate_overrules_approving_verifier(settings, fault):
    result = await ask(
        "Compare storm briefing reports.",
        settings=settings,
        trace_dir=None,
        faults={"writer": fault, "verifier": "approve_all"},
    )
    assert not result.verified and not result.claims and result.revisions == 1
    assert "fabricated.example" not in result.answer
    assert result.trace["model_calls"] == 7


async def test_one_revision_can_repair(settings):
    result = await ask(
        "What happened at the AI laboratory?",
        settings=settings,
        trace_dir=None,
        faults={"writer": "repair_once"},
    )
    assert result.verified and result.revisions == 1 and result.trace["model_calls"] == 7


async def test_verifier_rejects_otherwise_valid_draft(settings):
    result = await ask(
        "What happened at the AI laboratory?",
        settings=settings,
        trace_dir=None,
        faults={"verifier": "reject_all"},
    )
    assert not result.verified and result.revisions == 1
    assert "verifier_rejected" in result.failure_category


async def test_no_evidence(settings):
    result = await ask("What is the unicorn stock price?", settings=settings, trace_dir=None)
    assert result.status == "insufficient_evidence" and not result.claims


async def test_article_injection_cannot_pass_even_with_model_approval(settings):
    result = await ask(
        "Inspect the adversarial article.",
        settings=settings,
        trace_dir=None,
        faults={"verifier": "approve_all"},
    )
    assert not result.verified and not result.claims
    assert "untrusted_instructions" in result.failure_category
    assert "ignore previous" not in result.answer.lower()
    assert result.trace["tools"] == ["giim_search_events", "giim_get_event"]


@pytest.mark.parametrize(
    "fault,code",
    [
        ("unauthorized_tool", "unauthorized_tool"),
        ("loop", "tool_round_budget"),
        ("detail_overflow", "event_detail_budget"),
        ("malformed_tool", "invalid_tool_contract"),
    ],
)
async def test_programmatic_tool_budgets(settings, fault, code):
    result = await ask(
        "Retrieve all budget events.",
        settings=settings,
        trace_dir=None,
        faults={"researcher": fault},
    )
    assert not result.verified and code in result.failure_category
    assert result.trace["tool_calls"] <= 9 and result.trace["detail_calls"] <= 5
    assert result.trace["tool_rounds"] <= 3
    assert "execute_shell" not in result.trace["tools"]


async def test_token_and_time_limits(settings):
    result = await ask(
        "AI laboratory", settings=settings, trace_dir=None, limits=Limits(token_upper_bound=1000)
    )
    assert not result.verified and result.failure_category == "model_budget"
    result = await ask(
        "AI laboratory", settings=settings, trace_dir=None, limits=Limits(timeout=0.001)
    )
    assert not result.verified and result.failure_category == "request_timeout"


async def test_concurrent_session_isolation(settings):
    a, b = await asyncio.gather(
        ask("AI laboratory", settings=settings, trace_dir=None),
        ask("Orbital telescope", settings=settings, trace_dir=None),
    )
    assert a.verified and b.verified and a.request_id != b.request_id
    assert {c.citation.event_id for c in a.claims}.isdisjoint(
        {c.citation.event_id for c in b.claims}
    )
    empty = await ask("An unknown unrelated question", settings=settings, trace_dir=None)
    assert not empty.claims


@pytest.mark.parametrize("question", ["", " ", "q" * 301])
async def test_malformed_questions_rejected_before_tools(question):
    with pytest.raises(ValueError):
        await ask(question, trace_dir=None)
