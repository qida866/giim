"""密钥去敏、用量/费用和实时调用的显式授权边界。"""

import pytest
from google.genai.types import GenerateContentResponseUsageMetadata

from giim_agent.config import pricing
from giim_agent.roles import make_model
from giim_agent.runtime import stdio_target
from giim_agent.trace import Trace
from giim_mcp.config import Settings


def test_usage_cost_and_private_logs(tmp_path, monkeypatch):
    secret = "test-only-private-value-123456"
    monkeypatch.setenv("GOOGLE_API_KEY", secret)
    trace = Trace(
        "Check API_KEY=" + secret,
        "fake",
        tmp_path,
        {"test": {"input_per_million": 2, "output_per_million": 4}},
    )
    trace.emit("tool", arguments={"token": secret, "query": secret}, tool="giim_search_events")
    trace.model(
        "writer",
        "test",
        0.5,
        GenerateContentResponseUsageMetadata(
            prompt_token_count=100,
            candidates_token_count=20,
            thoughts_token_count=5,
            total_token_count=125,
        ),
    )
    summary = trace.finish("verified", True, 0)
    assert summary["total_tokens"] == 125
    assert summary["estimated_cost_usd"] == pytest.approx(0.0003)
    raw = (tmp_path / (trace.request_id + ".jsonl")).read_text()
    assert secret not in raw and "[REDACTED]" in raw
    assert "GOOGLE_API_KEY" not in stdio_target(Settings()).env
    assert not any(k for k in stdio_target(Settings()).env if "PASSWORD" in k)


def test_unknown_usage_remains_null():
    trace = Trace("question", "fake")
    trace.model("researcher", "fake", 0.1)
    assert trace.finish("insufficient_evidence", False, 0)["estimated_cost_usd"] is None


def test_live_requires_both_opt_in_and_key(monkeypatch):
    monkeypatch.delenv("GIIM_ENABLE_LIVE_GEMINI", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ValueError):
        make_model("writer", True)
    monkeypatch.setenv("GIIM_ENABLE_LIVE_GEMINI", "1")
    with pytest.raises(ValueError):
        make_model("writer", True)
    assert make_model("writer", False).model == "giim-fake-v1"


def test_live_sdk_construction_without_network(monkeypatch):
    monkeypatch.setenv("GIIM_ENABLE_LIVE_GEMINI", "1")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("GIIM_RESEARCHER_MODEL", "gemini-3.6-flash")
    model = make_model("researcher", True)
    assert model.model == "gemini-3.6-flash" and model.retry_options.attempts == 2
    assert model.client_kwargs["vertexai"] is False
    # 不访问 api_client，也不调用 generate_content。


@pytest.mark.parametrize(
    "value",
    [
        "[]",
        '{"m":{"input_per_million":-1,"output_per_million":2}}',
        '{"m":{"input_per_million":NaN,"output_per_million":2}}',
    ],
)
def test_invalid_pricing(monkeypatch, value):
    monkeypatch.setenv("GIIM_MODEL_PRICES", value)
    with pytest.raises(ValueError):
        pricing()


def test_summary_empty_partial_and_mixed_usage(tmp_path):
    from giim_agent.stats import summarize

    empty = summarize(tmp_path)
    assert empty["total_requests"] == 0 and empty["p95_latency_seconds"] is None
    (tmp_path / "partial.jsonl").write_text('{"request_id":"incomplete","kind":"request"}\n{broken')
    trace = Trace("valid", "fake", tmp_path)
    trace.model("writer", "fake", 0.1)
    trace.finish("verified", True, 0)
    summary = summarize(tmp_path)
    assert summary["total_requests"] == 2 and summary["incomplete_requests"] == 1
    assert summary["malformed_lines"] == 1 and summary["successful_requests"] == 1
    assert summary["mean_estimated_cost_usd"] is None and summary["mean_total_tokens"] is None
    assert summary["tokens_per_second"] is None


def test_third_party_logs_do_not_print_secret_or_exception(tmp_path, monkeypatch):
    import io
    import logging
    from giim_agent.logging import PrivateLogFilter

    monkeypatch.setenv("GOOGLE_API_KEY", "test-only-sensitive-canary")
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.addFilter(PrivateLogFilter())
    logger = logging.getLogger("giim_test_redaction")
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)
    try:
        try:
            raise ValueError("test-only-sensitive-canary")
        except ValueError:
            logger.exception("Provider key=%s", "test-only-sensitive-canary")
    finally:
        logger.removeHandler(handler)
    assert "test-only-sensitive-canary" not in output.getvalue()
    assert "[REDACTED]" in output.getvalue() and "Traceback" not in output.getvalue()


def test_failed_attempt_does_not_turn_partial_usage_into_total_cost(tmp_path):
    import json
    from giim_agent.stats import summarize

    trace = Trace(
        "Authored question",
        "fake",
        tmp_path,
        {"test": {"input_per_million": 2, "output_per_million": 4}},
    )
    trace.emit("model_start", role="researcher", model="test")
    trace.model(
        "researcher",
        "test",
        0.1,
        GenerateContentResponseUsageMetadata(
            prompt_token_count=100, candidates_token_count=20, total_token_count=120
        ),
    )
    trace.emit("model_start", role="writer", model="test")
    result = trace.finish("error", False, 0, "execution_error")
    assert result["model_calls"] == 1 and result["model_attempts"] == 2
    assert result["estimated_cost_usd"] is None and result["total_tokens"] is None
    # Reproduce historical partially-priced complete events; reader must not trust them.
    path = tmp_path / (trace.request_id + ".jsonl")
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[-1].update(estimated_cost_usd=0.00028, total_tokens=120)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    summary = summarize(tmp_path)
    assert summary["priced_requests"] == 0 and summary["measured_token_requests"] == 0
    assert summary["unreported_model_attempts"] == 1
    assert summary["known_response_estimate_usd"] == pytest.approx(0.00028)
    assert summary["total_estimated_cost_usd"] is None
