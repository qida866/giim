"""确定性 BaseLlm 测试替身；真正产生 ADK 函数调用，不绕过 MCP。"""

import json
from collections.abc import AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import PrivateAttr
from giim_mcp.fixtures import select

from .security import suspicious


def response(data: dict | None = None, calls: list[tuple[str, dict]] | None = None) -> LlmResponse:
    parts = (
        [types.Part(function_call=types.FunctionCall(name=name, args=args)) for name, args in calls]
        if calls
        else [types.Part(text=json.dumps(data))]
    )
    return LlmResponse(content=types.Content(role="model", parts=parts))


def payload(request: LlmRequest) -> dict:
    for content in reversed(request.contents):
        for part in content.parts or []:
            if part.text:
                try:
                    parsed = json.loads(part.text)
                    if isinstance(parsed, dict) and "question" in parsed:
                        return parsed
                except ValueError:
                    continue
    return {}


class FakeModel(BaseLlm):
    model: str = "giim-fake-v1"
    role: str
    fault: str = "none"
    _calls: int = PrivateAttr(default=0)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self._calls += 1
        if self.role == "researcher":
            yield self.research(llm_request)
        elif self.role == "writer":
            yield self.draft(payload(llm_request))
        else:
            yield self.verify(payload(llm_request))

    def research(self, request: LlmRequest) -> LlmResponse:
        texts = [part.text for c in request.contents for part in c.parts or [] if part.text]
        question = next((text for text in texts if text), "AI laboratory")
        results = [
            part.function_response.response
            for c in request.contents
            for part in c.parts or []
            if part.function_response
        ]
        if self.fault == "unauthorized_tool":
            return response(calls=[("execute_shell", {"command": "printenv"})])
        if self.fault == "loop" or not results:
            name = "giim_search_events"
            args = {"query": question[:300], "limit": 7 if self.fault == "detail_overflow" else 5}
            if "coverage" in question.casefold():
                name, args = "giim_get_coverage", {}
            elif "readiness" in question.casefold():
                name, args = "giim_check_ready", {}
            if self.fault == "malformed_tool":
                args = {"query": ""}
            return response(calls=[(name, args)])
        data = [result.get("data") or {} for result in results]
        details = [item for item in data if item.get("kind") == "detail"]
        lists = [item for item in data if item.get("kind") == "listing"]
        if lists and not details:
            ids = [row["id"] for row in lists[-1]["events"]]
            ids = ids[: 6 if self.fault == "detail_overflow" else 5]
            if ids:
                return response(
                    calls=[("giim_get_event", {"event_id": event_id}) for event_id in ids]
                )
        return response(
            {
                "event_ids": [d["event"]["id"] for d in details][:5],
                "insufficient": not details,
                "contradictions": len(details) > 1,
                "notes": "Scripted model; no semantic quality measurement.",
            }
        )

    def draft(self, data: dict) -> LlmResponse:
        if self.fault == "invalid_json":
            return LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text="not JSON")])
            )
        claims = [
            {
                "quote": source["excerpt"],
                "citation": {
                    key: source[key] for key in ("event_id", "article_id", "publisher", "url")
                },
            }
            for source in data.get("evidence", [])
        ]
        if claims and (self.fault != "repair_once" or self._calls == 1):
            if self.fault in ("bad_url", "repair_once"):
                claims[0]["citation"]["url"] = "https://fabricated.example.org/no-evidence"
            elif self.fault == "bad_event":
                claims[0]["citation"]["event_id"] = "ffffffff-ffff-ffff-ffff-ffffffffffff"
            elif self.fault == "bad_article":
                claims[0]["citation"]["article_id"] = 999999999
            elif self.fault == "unsupported":
                claims[0]["quote"] = "An unsupported invented conclusion."
            elif self.fault == "omit_conflict":
                claims = claims[:1]
        return response(
            {"claims": claims, "acknowledge_uncertainty": self.fault != "omit_uncertainty"}
        )

    def verify(self, data: dict) -> LlmResponse:
        if self.fault == "approve_all":
            return response({"ok": True, "unsupported_claims": [], "missing_citations": []})
        if self.fault == "reject_all":
            return response(
                {
                    "ok": False,
                    "unsupported_claims": ["synthetic reviewer rejection"],
                    "missing_citations": [],
                }
            )
        claims = data.get("draft", {}).get("claims", [])
        evidence = data.get("evidence", [])
        problems = []
        # 假模型仅理解明确标注的原创测试世界，不能把任意检索命中当成相关证据。
        # 真实新闻的语义相关性仍须通过另行授权的真实模型验证。
        expected_events = {row["event"]["id"] for row in select(data.get("question", ""))}
        if not expected_events or any(s["event_id"] not in expected_events for s in evidence):
            problems.append("evidence outside the scripted question's authored fixture scope")
        for claim in claims:
            citation = claim["citation"]
            if not any(
                all(citation.get(k) == s.get(k) for k in citation)
                and claim["quote"] == s.get("excerpt")
                for s in evidence
            ):
                problems.append("citation or quote mismatch")
            if suspicious(claim["quote"]):
                problems.append("instruction-bearing source")
        return response(
            {
                "ok": bool(claims) and not problems,
                "unsupported_claims": problems,
                "missing_citations": [],
            }
        )
