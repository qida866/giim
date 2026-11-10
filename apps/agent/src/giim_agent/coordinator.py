"""根 ADK 工作流：研究、草稿、独立审查、确定性门禁，最多一次修订。"""

import json
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from pydantic import ConfigDict, ValidationError

from .ledger import Ledger
from .schemas import Draft, ResearchBundle, Verification
from .trace import Trace


def state_event(values: dict) -> Event:
    return Event(author="coordinator", actions=EventActions(state_delta=values))


class Coordinator(BaseAgent):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    ledger: Ledger
    trace: Trace

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        researcher, writer, verifier = self.sub_agents
        self.trace.emit("role", role="coordinator")
        self.trace.emit("role", role="researcher")
        async for event in researcher.run_async(ctx):
            yield event
        research = ResearchBundle.model_validate(ctx.session.state.get("research", {}))
        if any(event_id not in self.ledger.details for event_id in research.event_ids):
            self.ledger.blocked.add("unretrieved_research_reference")
        yield state_event(
            {"evidence": self.ledger.evidence(), "research": research.model_dump(mode="json")}
        )
        accepted = None
        errors = []
        for iteration in range(2):
            self.trace.emit("role", role="writer", iteration=iteration)
            yield state_event(
                {"draft": None, "verification": None, "errors": errors, "revisions": iteration}
            )
            async for event in writer.run_async(ctx):
                yield event
            try:
                draft = Draft.model_validate(ctx.session.state.get("draft"))
            except (ValidationError, TypeError):
                errors = ["invalid_draft"]
                continue
            self.trace.emit("role", role="verifier", iteration=iteration)
            async for event in verifier.run_async(ctx):
                yield event
            try:
                verdict = Verification.model_validate(ctx.session.state.get("verification"))
                model_ok = (
                    verdict.ok and not verdict.unsupported_claims and not verdict.missing_citations
                )
            except (ValidationError, TypeError):
                model_ok = False
            errors = self.ledger.validate(draft)
            if not model_ok:
                errors.append("verifier_rejected")
            self.trace.emit(
                "verification",
                role="coordinator",
                model_ok=model_ok,
                deterministic_ok=not self.ledger.validate(draft),
                errors=errors,
                iteration=iteration,
            )
            if not errors:
                accepted = draft.model_dump(mode="json")
                break
        yield state_event({"accepted": accepted, "errors": errors})
        yield Event(
            author="coordinator",
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        text=json.dumps({"verified": accepted is not None, "errors": errors})
                    )
                ],
            ),
        )
