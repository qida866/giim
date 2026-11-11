"""Network-free tests of actual retry wrapper, budget and complete ADK/MCP execution."""

import asyncio
import json
from types import SimpleNamespace

import aiohttp
import httpx
import httpx2
import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from google.genai.errors import ClientError, ServerError
from pydantic import ConfigDict, SkipValidation

from giim_agent.budget import Budget, Limits
from giim_agent.fake import FakeModel
from giim_agent.hooks import Hooks
from giim_agent.retry import RetryingModel, retry_delay
from giim_agent.runtime import ask
from giim_agent.security import SafetyError
from giim_agent.trace import Trace


def unavailable():
    return ServerError(503, {"error": {"message": "private-provider-message-canary"}})


class Scripted(BaseLlm):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    script: SkipValidation[list]
    calls: int = 0

    async def generate_content_async(self, llm_request, stream=False):
        assert llm_request.config.http_options.retry_options.attempts == 1
        self.calls += 1
        item = self.script[min(self.calls - 1, len(self.script) - 1)]
        if isinstance(item, BaseException):
            raise item
        yield LlmResponse(
            content=types.Content(parts=[types.Part(text="{}")]),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=100, candidates_token_count=10, total_token_count=110
            ),
        )
        if item == "partial":
            raise unavailable()


async def configured(script, limits=None):
    budget, trace = Budget(limits or Limits()), Trace("authored", "fake")
    hooks = Hooks(budget, trace)
    model = RetryingModel(
        model="test",
        delegate=Scripted(model="test", script=script),
        role="writer",
        budget=budget,
        trace=trace,
    )
    context = SimpleNamespace(
        agent_name="writer",
        state={},
        get_invocation_context=lambda: SimpleNamespace(
            agent=SimpleNamespace(canonical_model=model)
        ),
    )
    request = LlmRequest(model="test", config=types.GenerateContentConfig())
    await hooks.before(context, request)
    return model, request, hooks, context


@pytest.fixture
def instant_wait(monkeypatch):
    waits = []

    async def sleep(delay):
        waits.append(delay)

    monkeypatch.setattr("giim_agent.retry.asyncio.sleep", sleep)
    return waits


async def consume(model, request, hooks, context):
    async for response in model.generate_content_async(request):
        await hooks.after(context, response)


async def test_transient_503_recovers_and_unknown_attempt_is_not_free(instant_wait):
    model, request, hooks, ctx = await configured([unavailable(), "ok"])
    await consume(model, request, hooks, ctx)
    assert model.delegate.calls == model.budget.models == 2
    assert len(instant_wait) == 1 and 0.25 <= instant_wait[0] <= 0.5
    summary = model.trace.finish("verified", True, 0)
    assert summary["retry_attempts"] == summary["provider_errors"] == 1
    assert summary["provider_recoveries"] == 1 and summary["model_attempts"] == 2
    assert summary["estimated_cost_usd"] is None and summary["total_tokens"] is None
    assert "private-provider-message-canary" not in json.dumps(model.trace.events)


async def test_retry_exhaustion_has_exactly_three_attempts(instant_wait):
    model, request, hooks, ctx = await configured([unavailable()])
    with pytest.raises(ServerError):
        await consume(model, request, hooks, ctx)
    assert model.delegate.calls == model.budget.models == 3
    assert len(instant_wait) == 2
    assert model.trace.events[-1]["reason"] == "exhausted"


@pytest.mark.parametrize("code", [408, 429, 500, 502, 503, 504])
async def test_transient_status_allowlist(code, instant_wait):
    error = (ClientError if code < 500 else ServerError)(code, {"error": {"message": "private"}})
    model, request, hooks, ctx = await configured([error, "ok"])
    await consume(model, request, hooks, ctx)
    assert model.delegate.calls == 2


@pytest.mark.parametrize(
    "error",
    [
        ClientError(400, {}),
        ClientError(401, {}),
        ClientError(403, {}),
        ServerError(501, {}),
        ValueError("malformed"),
        SafetyError("unsafe"),
    ],
)
async def test_permanent_and_validation_errors_never_retry(error, instant_wait):
    model, request, hooks, ctx = await configured([error])
    with pytest.raises(type(error)):
        await consume(model, request, hooks, ctx)
    assert model.delegate.calls == 1 and not instant_wait


@pytest.mark.parametrize(
    "error",
    [
        httpx.ReadTimeout("private"),
        httpx.ConnectError("private"),
        httpx2.ReadTimeout("private"),
        httpx2.ConnectError("private"),
        aiohttp.ClientConnectionError("private"),
        TimeoutError(),
    ],
)
async def test_transport_timeouts_are_bounded(error, instant_wait):
    model, request, hooks, ctx = await configured([error, "ok"])
    await consume(model, request, hooks, ctx)
    assert model.delegate.calls == 2


@pytest.mark.parametrize("limit", ["calls", "tokens", "disabled"])
async def test_request_budget_or_retry_setting_prevents_extra_attempt(limit, instant_wait):
    limits = Limits(
        model_calls=1 if limit == "calls" else 10, provider_retries=0 if limit == "disabled" else 2
    )
    model, request, hooks, ctx = await configured([unavailable()], limits)
    if limit == "tokens":
        limits.token_upper_bound = model.budget.reserved
    with pytest.raises((SafetyError, ServerError)):
        await consume(model, request, hooks, ctx)
    assert model.delegate.calls == model.budget.models == 1 and not instant_wait


async def test_partial_response_never_replayed(instant_wait):
    model, request, hooks, ctx = await configured(["partial", "ok"])
    with pytest.raises(ServerError):
        await consume(model, request, hooks, ctx)
    assert model.delegate.calls == 1 and not instant_wait
    assert any(e.get("partial_response") for e in model.trace.events)


async def test_cancellation_during_backoff_does_not_start_retry(monkeypatch):
    model, request, hooks, ctx = await configured([unavailable()])

    async def cancelled(delay):
        raise asyncio.CancelledError()

    monkeypatch.setattr("giim_agent.retry.asyncio.sleep", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await consume(model, request, hooks, ctx)
    assert model.delegate.calls == model.budget.models == 1


def test_equal_jitter_grows_and_is_capped():
    for index in range(8):
        values = [retry_delay(index) for _ in range(20)]
        maximum = min(4, 0.5 * 2**index)
        assert all(maximum / 2 <= v <= maximum for v in values)
        assert len(set(values)) > 1
    for invalid in [-1, 3, True]:
        with pytest.raises(ValueError):
            Limits(provider_retries=invalid)


@pytest.mark.parametrize(
    "fault", ["none", "bad_url", "unsupported", "omit_uncertainty", "omit_conflict"]
)
async def test_real_adk_mcp_workflow_recovers_verifier_but_does_not_bypass_gate(
    settings, tmp_path, instant_wait, fault
):
    class UnavailableVerifier(FakeModel):
        attempts: int = 0

        async def generate_content_async(self, llm_request, stream=False):
            self.attempts += 1
            if self.role == "verifier" and self.attempts == 1:
                raise unavailable()
            async for reply in super().generate_content_async(llm_request, stream):
                yield reply

    answer = await ask(
        "storm",
        settings=settings,
        trace_dir=tmp_path,
        faults={"writer": fault},
        model_factory=lambda role, live, override, fault: UnavailableVerifier(
            role=role, fault=fault
        ),
    )
    assert answer.verified is (fault == "none")
    assert answer.trace["retry_attempts"] == 1 and answer.trace["provider_recoveries"] == 1
    assert answer.trace["model_attempts"] <= 10
    if fault != "none":
        assert not answer.claims


async def test_wall_clock_deadline_interrupts_backoff():
    model, request, hooks, ctx = await configured([unavailable()])
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.01):
            await consume(model, request, hooks, ctx)
    assert model.delegate.calls == 1


async def test_pinned_gemini_sdk_http_503_has_no_hidden_retry(monkeypatch, instant_wait):
    """Real pinned GenAI/ADK HTTP serialization, local stub only; no Google endpoint."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from giim_agent.roles import make_model
    from giim_agent.schemas import DraftOutput

    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            failed = len(requests) == 1
            payload = (
                {
                    "error": {
                        "code": 503,
                        "message": "private-provider-message-canary",
                        "status": "UNAVAILABLE",
                    }
                }
                if failed
                else {
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [{"text": '{"claims":[],"acknowledge_uncertainty":true}'}],
                            },
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 100,
                        "candidatesTokenCount": 10,
                        "totalTokenCount": 110,
                    },
                    "modelVersion": "gemini-3.5-flash-lite",
                }
            )
            body = json.dumps(payload).encode()
            self.send_response(503 if failed else 200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("GIIM_ENABLE_LIVE_GEMINI", "1")
    monkeypatch.setenv("GOOGLE_API_KEY", "synthetic-http-test-canary")
    model, request, hooks, ctx = await configured(["unused"])
    delegate = make_model("writer", True, "gemini-3.5-flash-lite")
    delegate.client_kwargs["http_options"] = types.HttpOptions(
        base_url=f"http://127.0.0.1:{server.server_port}",
        api_version="v1beta",
        retry_options=types.HttpRetryOptions(attempts=1),
        timeout=2000,
    )
    model.delegate = delegate
    request.model = "gemini-3.5-flash-lite"
    request.config.response_json_schema = DraftOutput.model_json_schema()
    request.config.response_mime_type = "application/json"
    try:
        await consume(model, request, hooks, ctx)
        assert len(requests) == 2
        assert sum(e["kind"] == "provider_error" for e in model.trace.events) == 1
        assert sum(e["kind"] == "provider_retry" for e in model.trace.events) == 1
        assert len(instant_wait) == 1
        wire = requests[-1]["generationConfig"]
        assert wire["responseMimeType"] == "application/json"
        assert "responseSchema" not in wire
        assert "acknowledge_uncertainty" in wire["responseJsonSchema"]["required"]
    finally:
        await delegate.api_client.aio.aclose()
        delegate.api_client.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
