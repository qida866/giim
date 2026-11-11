"""Preparation guards run with network disabled and never contact Gemini."""

import importlib.util
import json
from pathlib import Path
import sys

import pytest
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from giim_agent.security import SafetyError

spec = importlib.util.spec_from_file_location(
    "live_trial", Path(__file__).resolve().parents[3] / "scripts/live_gemini_trial.py"
)
trial = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = trial
spec.loader.exec_module(trial)


def request():
    return LlmRequest(
        model=trial.MODEL,
        contents=[types.Content(parts=[types.Part(text="authored")])],
        config=types.GenerateContentConfig(max_output_tokens=2048),
    )


def test_reservation_limits_and_missing_usage():
    meter = trial.Meter(calls=50)
    with pytest.raises(SafetyError, match="trial_budget"):
        meter.reserve(request())
    meter = trial.Meter(reserved_usd=0.95)
    with pytest.raises(SafetyError, match="trial_budget"):
        meter.reserve(request())
    with pytest.raises(SafetyError, match="trial_missing_usage"):
        trial.Meter().observe(LlmResponse(), "researcher")


def test_usage_estimate_and_overrun_stop():
    meter = trial.Meter()
    meter.reserve(request())
    assert meter.estimated_usd is None
    meter.observe(
        LlmResponse(
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=100, candidates_token_count=20, thoughts_token_count=5
            )
        ),
        "writer",
    )
    assert meter.observed_usd == pytest.approx(0.0000925)
    assert meter.estimated_usd == meter.observed_usd
    with pytest.raises(SafetyError, match="trial_usage_exceeded_reservation"):
        meter.observe(
            LlmResponse(
                usage_metadata=types.GenerateContentResponseUsageMetadata(
                    prompt_token_count=100, candidates_token_count=2049
                )
            ),
            "writer",
        )


@pytest.mark.parametrize("terminal", [False, True])
def test_injection_preserves_real_usage_and_handles_structured_terminal_tool(terminal):
    draft = {
        "claims": [
            {
                "quote": "Authored excerpt.",
                "citation": {
                    "event_id": trial.identifier(1),
                    "article_id": 101,
                    "publisher": "Authored Demo en",
                    "url": "https://demo.example.org/1/1",
                },
            }
        ],
        "acknowledge_uncertainty": True,
    }
    part = (
        types.Part(function_call=types.FunctionCall(name="set_model_response", args=draft))
        if terminal
        else types.Part(text=json.dumps(draft))
    )
    response = LlmResponse(
        content=types.Content(parts=[part]),
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=10),
    )
    assert trial.corrupt_draft(response)
    data = (
        response.content.parts[0].function_call.args
        if terminal
        else json.loads(response.content.parts[0].text)
    )
    assert data["claims"][0]["citation"]["event_id"] == trial.BAD_ID
    assert data["claims"][0]["citation"]["url"] == trial.BAD_URL
    assert response.usage_metadata.prompt_token_count == 10


async def test_missing_approval_stops_before_preflight(monkeypatch, tmp_path):
    from argparse import Namespace

    monkeypatch.delenv("GIIM_LIVE_TRIAL_APPROVAL", raising=False)
    with pytest.raises(SafetyError, match="trial_approval"):
        await trial.run(
            Namespace(live=True, output=tmp_path / "unused", api="http://127.0.0.1:8000")
        )
    assert not (tmp_path / "unused").exists()


def test_pinned_model_configuration_has_no_retries(monkeypatch):
    monkeypatch.setenv("GIIM_ENABLE_LIVE_GEMINI", "1")
    monkeypatch.setenv("GOOGLE_API_KEY", "synthetic-test-canary")
    monkeypatch.delenv("GIIM_RESEARCHER_MODEL", raising=False)
    meter, records = trial.Meter(), []
    built = trial.factory(meter, records)("researcher", True, None, "none")
    assert built.meter is meter and built.records is records
    assert built.delegate.model == "gemini-3.5-flash-lite"
    assert built.delegate.retry_options.attempts == 1
    assert built.delegate.client_kwargs["vertexai"] is False
    monkeypatch.setenv("GIIM_RESEARCHER_MODEL", "gemini-unapproved-model")
    with pytest.raises(SafetyError, match="trial_model_override"):
        trial.factory(trial.Meter(), [])("researcher", True, None, "none")


@pytest.mark.parametrize("corrupt", [False, True])
async def test_trial_wrapper_through_adk_mcp_without_network_provider(
    monkeypatch, settings, tmp_path, corrupt
):
    from giim_agent.fake import FakeModel
    from giim_agent.runtime import ask

    class UsageFake(FakeModel):
        async def generate_content_async(self, llm_request, stream=False):
            async for reply in super().generate_content_async(llm_request, stream):
                reply.usage_metadata = types.GenerateContentResponseUsageMetadata(
                    prompt_token_count=100, candidates_token_count=50, total_token_count=150
                )
                yield reply

    def local_model(role, live, override):
        # Explicit fixture model only; this test never instantiates a Gemini client.
        fake = UsageFake(role=role, model=trial.MODEL)
        return fake

    # Factory construction expects the real adapter's retry field; bypass that factory
    # here while testing the identical bounded wrapper and live-mode runtime workflow.
    meter, records = trial.Meter(), []

    def local_factory(role, live, override, fault):
        return trial.TrialModel(
            model=trial.MODEL,
            delegate=local_model(role, live, override),
            role=role,
            meter=meter,
            records=records,
            corrupt=corrupt,
        )

    result = await ask(
        "AI laboratory",
        settings=settings,
        live=True,
        limits=trial.LIMITS,
        prices=trial.PRICES,
        trace_dir=tmp_path,
        model_factory=local_factory,
    )
    assert meter.calls == result.trace["model_calls"]
    assert result.trace["estimated_cost_usd"] == pytest.approx(meter.observed_usd)
    assert result.verified is not corrupt
    if corrupt:
        assert any(row.get("injected") for row in records)
        assert "unknown_evidence_reference" in result.failure_category
    else:
        assert len(result.claims) == 3


def test_resume_retains_budget_and_never_repeats_completed_workflows(tmp_path):
    prior = {
        "model": trial.MODEL,
        "attempted_model_calls": 3,
        "reserved_usd": 0.0224001,
        "observed_estimated_usd": 0.0019991,
        "results": [
            {"case": "A", "answer": {"trace": {"model_calls": 3}}},
            {"case": "B", "status": "BLOCKED"},
        ],
    }
    path = tmp_path / "results.json"
    path.write_text(json.dumps(prior))
    meter, completed = trial.resume_state(path)
    assert meter.calls == 3 and meter.reserved_usd == 0.0224001
    assert meter.estimated_usd == 0.0019991
    assert [r["case"] for r in completed] == ["A"]
    assert [case for case, _ in trial.CASES[len(completed) :]] == list("BCDE")
    meter.calls = 50
    with pytest.raises(SafetyError, match="trial_budget"):
        meter.reserve(request())
    for key, value in [
        ("observed_estimated_usd", None),
        ("reserved_usd", 0.95),
        ("attempted_model_calls", 51),
        ("reserved_usd", float("nan")),
    ]:
        invalid = {**prior, key: value}
        path.write_text(json.dumps(invalid))
        with pytest.raises(SafetyError):
            trial.resume_state(path)


def test_investigated_unreported_attempt_keeps_full_reservation_and_unknown_cost(tmp_path):
    prior = {
        "model": trial.MODEL,
        "attempted_model_calls": 7,
        "reserved_usd": 0.0517271,
        "observed_estimated_usd": None,
        "known_response_estimate_usd": 0.0040313,
        "results": [
            {"case": "A", "answer": {"trace": {"model_calls": 3}}},
            {"case": "B", "answer": {"trace": {"model_calls": 3}}},
        ],
    }
    path = tmp_path / "results.json"
    path.write_text(json.dumps(prior))
    with pytest.raises(SafetyError):
        trial.resume_state(path)
    meter, completed = trial.resume_state(path, carry_unreported=True)
    assert meter.calls == 7 and meter.reserved_usd == 0.0517271
    assert meter.observed_usd == 0.0040313 and meter.estimated_usd is None
    assert [case for case, _ in trial.CASES[len(completed) :]] == list("CDE")
    meter.reserve(request())
    meter.observe(
        LlmResponse(
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=100, candidates_token_count=20
            )
        ),
        "writer",
    )
    assert meter.calls == 8 and meter.estimated_usd is None
    assert meter.reserved_usd > 0.0517271


async def test_provider_diagnostics_never_store_exception_message():
    from google.adk.models.base_llm import BaseLlm

    class Failing(BaseLlm):
        async def generate_content_async(self, llm_request, stream=False):
            raise ValueError("private-exception-canary")
            yield

    records = []
    model = trial.TrialModel(
        model=trial.MODEL,
        delegate=Failing(model=trial.MODEL),
        role="writer",
        meter=trial.Meter(),
        records=records,
    )
    with pytest.raises(ValueError):
        async for _ in model.generate_content_async(request()):
            pass
    assert records == [{"role": "writer", "exception_type": "ValueError"}]
    assert "private-exception-canary" not in json.dumps(records)


def test_retest_scope_and_budget_are_independent_and_smaller(tmp_path):
    approval, calls, cost, cases = trial.round_config("retest-abc")
    assert approval != trial.APPROVAL
    assert (calls, cost) == (30, 0.30)
    assert [case for case, _ in cases] == list("ABC")
    meter, completed = trial.resume_state(None, round_name="retest-abc")
    assert not completed and meter.max_calls == 30 and meter.max_usd == 0.30
    meter.calls = 30
    with pytest.raises(SafetyError, match="trial_budget"):
        meter.reserve(request())
    meter.calls, meter.reserved_usd = 0, 0.299
    with pytest.raises(SafetyError, match="trial_budget"):
        meter.reserve(request())
    prior = {
        "model": trial.MODEL,
        "attempted_model_calls": 3,
        "reserved_usd": 0.02,
        "observed_estimated_usd": 0.001,
        "results": [{"case": "A", "answer": {"trace": {"model_calls": 3}}}],
    }
    path = tmp_path / "prior.json"
    path.write_text(json.dumps(prior))
    with pytest.raises(SafetyError, match="resume_budget"):
        trial.resume_state(path, round_name="retest-abc")
    prior["round"] = "retest-abc"
    path.write_text(json.dumps(prior))
    resumed, done = trial.resume_state(path, round_name="retest-abc")
    assert resumed.calls == 3 and resumed.max_calls == 30 and resumed.reserved_usd == 0.02
    assert [case for case, _ in cases[len(done) :]] == list("BC")
    prior["results"].append({"case": "D", "answer": {"trace": {"model_calls": 0}}})
    path.write_text(json.dumps(prior))
    with pytest.raises(SafetyError, match="resume_cases"):
        trial.resume_state(path, round_name="retest-abc")


async def test_original_approval_cannot_authorize_retest(monkeypatch, tmp_path):
    from argparse import Namespace

    monkeypatch.setenv("GIIM_LIVE_TRIAL_APPROVAL", trial.APPROVAL)
    monkeypatch.setenv("GIIM_ENABLE_LIVE_GEMINI", "1")
    monkeypatch.setenv("GOOGLE_API_KEY", "synthetic-test-canary")
    with pytest.raises(SafetyError, match="trial_approval"):
        await trial.run(Namespace(live=True, round="retest-abc", output=tmp_path / "unused"))
    assert not (tmp_path / "unused").exists()


async def test_retest_dispatches_only_abc_and_preserves_existing_outputs(monkeypatch, tmp_path):
    from argparse import Namespace
    from types import SimpleNamespace

    monkeypatch.setenv("GIIM_LIVE_TRIAL_APPROVAL", trial.RETEST_APPROVAL)
    monkeypatch.setenv("GIIM_ENABLE_LIVE_GEMINI", "1")
    monkeypatch.setenv("GOOGLE_API_KEY", "synthetic-test-canary")
    called = []

    async def no_network_preflight(settings):
        return {}

    async def no_network_ask(question, **kwargs):
        called.append(question)
        trace = {"model_calls": 0}
        directory = kwargs["trace_dir"]
        directory.mkdir(exist_ok=True)
        (directory / "authored.jsonl").write_text("")
        return SimpleNamespace(
            request_id="authored",
            failure_category=None,
            status="verified",
            model_dump=lambda **_: {"trace": trace},
        )

    monkeypatch.setattr(trial, "preflight", no_network_preflight)
    monkeypatch.setattr(trial, "ask", no_network_ask)
    monkeypatch.setattr(trial, "checks", lambda *args: {"dispatch_test_only": True})
    args = Namespace(
        live=True, round="retest-abc", api="http://127.0.0.1:8000", output=tmp_path / "round2"
    )
    assert await trial.run(args) == 0
    assert called == [question for _, question in trial.CASES[:3]]
    saved = (args.output / "results.json").read_bytes()
    result = json.loads(saved)
    assert result["round"] == "retest-abc"
    assert [row["case"] for row in result["results"]] == list("ABC")
    with pytest.raises(FileExistsError):
        await trial.run(args)
    assert len(called) == 3 and (args.output / "results.json").read_bytes() == saved


@pytest.mark.parametrize("cap", ["none", "calls", "cost"])
async def test_provider_retries_share_trial_cost_and_call_meter(monkeypatch, cap):
    from google.genai.errors import ServerError
    from giim_agent.retry import RetryingModel
    from giim_agent.budget import Budget, Limits
    from giim_agent.trace import Trace
    from giim_agent.hooks import Hooks
    from types import SimpleNamespace

    class TemporaryProvider(trial.BaseLlm):
        calls: int = 0

        async def generate_content_async(self, request, stream=False):
            self.calls += 1
            if self.calls == 1:
                raise ServerError(503, {"error": {"message": "do-not-log-provider-body"}})
            yield LlmResponse(
                usage_metadata=types.GenerateContentResponseUsageMetadata(
                    prompt_token_count=100, candidates_token_count=20, total_token_count=120
                )
            )

    async def immediate(delay):
        pass

    monkeypatch.setattr("giim_agent.retry.asyncio.sleep", immediate)
    meter = trial.Meter(max_calls=1 if cap == "calls" else 20, max_usd=0.20)
    provider = TemporaryProvider(model=trial.MODEL)
    inner = trial.TrialModel(
        model=trial.MODEL, delegate=provider, role="writer", meter=meter, records=[]
    )
    budget, trace = Budget(Limits()), Trace("authored", "fake")
    wrapped = RetryingModel(
        model=trial.MODEL, delegate=inner, role="writer", budget=budget, trace=trace
    )
    req = request()
    await Hooks(budget, trace).before(SimpleNamespace(agent_name="writer", state={}), req)
    if cap == "cost":
        preview = trial.Meter()
        preview.reserve(req)
        # First fits, second does not; failed attempt must retain its full reservation.
        meter.max_usd = preview.reserved_usd * 1.5
    if cap == "none":
        responses = [r async for r in wrapped.generate_content_async(req)]
        assert len(responses) == 1 and provider.calls == meter.calls == 2
        assert meter.observed_usd > 0 and meter.estimated_usd is None
    else:
        with pytest.raises(SafetyError, match="trial_budget"):
            _ = [r async for r in wrapped.generate_content_async(req)]
        assert provider.calls == meter.calls == 1 and meter.estimated_usd is None
    assert 0 < meter.reserved_usd < meter.max_usd


async def test_ab_profile_requires_new_approval_and_excludes_other_cases(monkeypatch, tmp_path):
    from argparse import Namespace

    approval, calls, ceiling, cases = trial.round_config("retest-ab")
    assert [c for c, _ in cases] == list("AB") and (calls, ceiling) == (20, 0.20)
    assert approval not in (trial.APPROVAL, trial.RETEST_APPROVAL)
    meter, done = trial.resume_state(None, round_name="retest-ab")
    assert not done and (meter.max_calls, meter.max_usd) == (20, 0.20)
    monkeypatch.setenv("GIIM_LIVE_TRIAL_APPROVAL", trial.RETEST_APPROVAL)
    with pytest.raises(SafetyError, match="trial_approval"):
        await trial.run(Namespace(live=True, round="retest-ab", output=tmp_path / "unused"))
    assert not (tmp_path / "unused").exists()


async def test_recovered_trial_keeps_unknown_cost_but_requires_verified_answer(
    monkeypatch, settings, tmp_path
):
    from google.genai.errors import ServerError
    from giim_agent.fake import FakeModel
    from giim_agent.runtime import ask

    class UsageProvider(FakeModel):
        calls: int = 0

        async def generate_content_async(self, request, stream=False):
            self.calls += 1
            if self.role == "verifier" and self.calls == 1:
                raise ServerError(503, {"error": {"message": "synthetic transient"}})
            async for reply in super().generate_content_async(request, stream):
                reply.usage_metadata = types.GenerateContentResponseUsageMetadata(
                    prompt_token_count=100, candidates_token_count=20, total_token_count=120
                )
                yield reply

    async def immediate(delay):
        pass

    monkeypatch.setattr("giim_agent.retry.asyncio.sleep", immediate)
    meter, records, evidence = trial.Meter(max_calls=20, max_usd=0.20), [], []

    def factory(role, live, override, fault):
        return trial.TrialModel(
            model=trial.MODEL,
            role=role,
            meter=meter,
            records=records,
            delegate=UsageProvider(role=role, model=trial.MODEL),
        )

    answer = await ask(
        "AI laboratory",
        live=True,
        settings=settings,
        model=trial.MODEL,
        model_factory=factory,
        prices=trial.PRICES,
        trace_dir=tmp_path,
        evidence_sink=evidence,
    )
    events = [
        json.loads(row)
        for row in (tmp_path / (answer.request_id + ".jsonl")).read_text().splitlines()
    ]
    assert answer.verified and meter.calls == 6 and len(meter.observations) == 5
    assert meter.estimated_usd is None and answer.trace["estimated_cost_usd"] is None
    checks = trial.checks("A", answer, evidence, events, records)
    assert all(checks.values()), checks
    # Removing the provider-error accounting must not magically turn missing usage into zero.
    assert not trial.checks(
        "A", answer, evidence, [e for e in events if e["kind"] != "provider_error"], records
    )["usage_accounted"]
