"""Regression for the real Gemini set_model_response path, absent from text-only fakes."""

import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from google.adk.tools.set_model_response_tool import SetModelResponseTool
from google.genai import types
from pydantic import ValidationError

from giim_agent.fake import FakeModel
from giim_agent.runtime import ask
from giim_agent.schemas import ResearchBundle, Draft, Verification


@pytest.mark.parametrize(
    "schema,payload",
    [
        (ResearchBundle, {"event_ids": ["00000000-0000-0000-0000-000000000001"]}),
        (
            Draft,
            {
                "claims": [
                    {
                        "quote": "Authored test.",
                        "citation": {
                            "event_id": "00000000-0000-0000-0000-000000000001",
                            "article_id": 101,
                            "publisher": "Authored Demo en",
                            "url": "https://demo.example.org/1/1",
                        },
                    }
                ]
            },
        ),
    ],
)
async def test_adk_terminal_tool_returns_json_safe_validated_identifiers(schema, payload):
    context = SimpleNamespace(actions=SimpleNamespace())
    result = await SetModelResponseTool(schema).run_async(args=payload, tool_context=context)
    # ADK serializes this dictionary with json.dumps; Python UUID instances must not escape.
    decoded = json.loads(json.dumps(result))
    restored = schema.model_validate(decoded)
    event_id = (
        restored.event_ids[0] if schema is ResearchBundle else restored.claims[0].citation.event_id
    )
    assert isinstance(event_id, UUID)
    assert decoded == schema.model_validate(payload).model_dump(mode="json")
    bad = (
        {"event_ids": ["not-a-uuid"]}
        if schema is ResearchBundle
        else {
            "claims": [
                {
                    **payload["claims"][0],
                    "citation": {**payload["claims"][0]["citation"], "event_id": "not-a-uuid"},
                }
            ]
        }
    )
    with pytest.raises(ValidationError):
        schema.model_validate(bad)


class TerminalResearch(FakeModel):
    async def generate_content_async(self, llm_request, stream=False):
        async for reply in super().generate_content_async(llm_request, stream):
            if self.role == "researcher" and reply.content and reply.content.parts[0].text:
                data = json.loads(reply.content.parts[0].text)
                reply.content.parts = [
                    types.Part(
                        function_call=types.FunctionCall(name="set_model_response", args=data)
                    )
                ]
            yield reply


async def test_terminal_research_response_reaches_writer_verifier_and_gate(settings):
    def factory(role, live, override, fault):
        return TerminalResearch(role=role, fault=fault)

    answer = await ask("AI laboratory", settings=settings, trace_dir=None, model_factory=factory)
    assert answer.verified, answer.failure_category
    assert len(answer.claims) == 3
    assert answer.trace["model_calls"] == 5


def test_pinned_genai_sdk_accepts_all_role_schemas():
    from google.genai import _transformers
    from giim_agent.schemas import Verification

    for schema in (ResearchBundle, Draft, Verification):
        converted = _transformers.t_schema(None, schema)
        assert converted is not None


@pytest.mark.parametrize("bad_id", [0, -1, True, "101"])
def test_citation_article_id_validation_remains_strict(bad_id):
    from giim_agent.schemas import Citation

    with pytest.raises(ValidationError):
        Citation(
            event_id="00000000-0000-0000-0000-000000000001",
            article_id=bad_id,
            publisher="Authored Demo en",
            url="https://demo.example.org/1/1",
        )


@pytest.mark.parametrize("role,schema", [("writer", Draft), ("verifier", Verification)])
async def test_roles_use_native_json_schema_without_weakening_local_validation(role, schema):
    from giim_agent.hooks import Hooks
    from giim_agent.budget import Budget, Limits
    from giim_agent.trace import Trace
    from google.adk.models.llm_request import LlmRequest

    context = SimpleNamespace(agent_name=role, state={"question": "Authored question"})
    request = LlmRequest(
        model="gemini-3.5-flash-lite", config=types.GenerateContentConfig(response_schema=schema)
    )
    await Hooks(Budget(Limits()), Trace("Authored question", "fake")).before(context, request)
    assert request.config.response_schema is None
    assert request.config.response_mime_type == "application/json"
    assert request.config.response_json_schema == schema.model_json_schema()
    assert schema.model_config["extra"] == "forbid"
    json.dumps(request.config.model_dump(mode="json", exclude_none=True))
