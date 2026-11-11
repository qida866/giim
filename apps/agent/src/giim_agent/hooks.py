"""ADK 回调：模型预算、角色输入隔离、工具轮次与可测用量。"""

import json
from time import perf_counter

from google.genai import types
from pydantic import BaseModel

from giim_mcp.inputs import INPUTS

from .budget import Budget
from .security import SafetyError
from .trace import Trace


class Hooks:
    def __init__(self, budget: Budget, trace: Trace):
        self.budget, self.trace = budget, trace
        self.started: dict[str, float] = {}

    async def before(self, callback_context, llm_request):
        role = callback_context.agent_name
        if role != "researcher":
            state = callback_context.state
            data = {
                key: state.get(key)
                for key in ("question", "evidence", "research", "draft", "errors")
            }
            data["validation_requirements"] = {
                "explicit_uncertainty_required": True,
                "uncertainty_must_be_true": len(state.get("evidence") or []) > 1,
                "preserve_all_current_sources": True,
                "quote_and_citation_must_match_evidence": True,
            }
            # 来源数据放入 user 内容，静态系统指令与证据分开。
            llm_request.contents = [
                types.Content(role="user", parts=[types.Part(text=json.dumps(data, default=str))])
            ]
        llm_request.config.max_output_tokens = self.budget.limits.output_tokens

        # Keep Pydantic validation in ADK/the Coordinator; send the documented JSON
        # Schema wire field rather than the narrower legacy Google Schema dialect.
        schema = llm_request.config.response_schema
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            wire_schema = schema.model_json_schema()
            if role == "writer" and len(callback_context.state.get("evidence") or []) > 1:
                # Google's documented enum subset covers strings/numbers, not booleans.
                # Keep the wire boolean compatible; enforce the value in the local gate.
                field = wire_schema["properties"]["acknowledge_uncertainty"]
                field["description"] = (
                    "Required value: true for this request's multiple current sources. "
                    + field.get("description", "")
                )
            llm_request.config.response_json_schema = wire_schema
            llm_request.config.response_schema = None
            llm_request.config.response_mime_type = "application/json"

        def encode_schema(value):
            if isinstance(value, type) and issubclass(value, BaseModel):
                return value.model_json_schema()
            return str(value)

        request_json = json.dumps(llm_request.model_dump(exclude_none=True), default=encode_schema)
        self.budget.model(len(request_json.encode()))
        self.started[role] = perf_counter()
        self.trace.emit("model_start", role=role, model=llm_request.model)
        return None

    async def after(self, callback_context, llm_response):
        role = callback_context.agent_name
        self.trace.model(
            role,
            callback_context.get_invocation_context().agent.canonical_model.model,
            perf_counter() - self.started[role],
            llm_response.usage_metadata,
        )
        if llm_response.error_code:
            raise SafetyError("model_error")
        parts = llm_response.content.parts if llm_response.content else []
        calls = [part.function_call for part in parts or [] if part.function_call]
        # ADK 可添加一个仅用于结构化响应的终止工具；它没有外部权限。
        external = [call for call in calls if call.name != "set_model_response"]
        if external:
            if role != "researcher" or any(call.name not in INPUTS for call in external):
                raise SafetyError("unauthorized_tool")
            self.budget.round()
        if len(llm_response.model_dump_json().encode()) > 24000:
            raise SafetyError("model_response_too_large")
        return None
