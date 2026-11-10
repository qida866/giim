"""ADK FunctionTool 到官方 MCP Client 的受限桥接。"""

from uuid import UUID

from google.adk.tools import FunctionTool
from mcp import Client
from pydantic import ValidationError
from time import perf_counter

from giim_mcp.inputs import INPUTS
from giim_mcp.models import Detail, Envelope, Listing

from .budget import Budget
from .ledger import Ledger
from .security import SafetyError
from .trace import Trace


class Gateway:
    def __init__(self, client: Client, budget: Budget, ledger: Ledger, trace: Trace):
        self.client, self.budget, self.ledger, self.trace = client, budget, ledger, trace

    async def call(self, name: str, args: dict) -> dict:
        if name not in INPUTS:
            raise SafetyError("unauthorized_tool")
        self.budget.tool(name)
        start = perf_counter()
        status = "error"
        try:
            valid = INPUTS[name].model_validate(args).model_dump(mode="json")
            if name == "giim_get_event" and UUID(valid["event_id"]) not in self.ledger.discovered:
                raise SafetyError("undiscovered_event")
            result = await self.client.call_tool(name, valid, read_timeout_seconds=25)
            if result.is_error:
                raise SafetyError("mcp_tool_error")
            envelope = Envelope.model_validate(result.structured_content)
            if not envelope.ok:
                code = envelope.error.code if envelope.error else "malformed_response"
                self.ledger.blocked.add(code)
                status = code
            else:
                if isinstance(envelope.data, Listing):
                    self.ledger.listing(envelope.data)
                elif isinstance(envelope.data, Detail):
                    if str(envelope.data.event.id) != valid.get("event_id"):
                        raise SafetyError("event_identity_mismatch")
                    self.ledger.detail(envelope.data, envelope.truncated)
                status = "ok"
            return envelope.model_dump(mode="json")
        except ValidationError:
            raise SafetyError("invalid_tool_contract") from None
        finally:
            self.trace.emit(
                "tool",
                role="researcher",
                tool=name,
                arguments=args,
                latency_seconds=perf_counter() - start,
                status=status,
            )

    def tools(self) -> list[FunctionTool]:
        async def giim_search_events(query: str, window: str = "7d", limit: int = 5) -> dict:
            """Search GIIM events for a question; returns candidates, not yet verified claims."""
            return await self.call(
                "giim_search_events", {"query": query, "window": window, "limit": limit}
            )

        async def giim_get_event(event_id: str) -> dict:
            """Retrieve current supporting sources for a previously discovered event UUID."""
            return await self.call("giim_get_event", {"event_id": event_id})

        async def giim_get_today_events(
            window: str = "24h", limit: int = 10, language: str | None = None
        ) -> dict:
            """List recent candidates; detail retrieval is required before citing an event."""
            return await self.call(
                "giim_get_today_events", {"window": window, "limit": limit, "language": language}
            )

        async def giim_get_coverage() -> dict:
            """Get observed coverage metadata; do not infer unsupported total counts."""
            return await self.call("giim_get_coverage", {})

        async def giim_check_ready() -> dict:
            """Check exposed readiness; search readiness may be unknown."""
            return await self.call("giim_check_ready", {})

        return [
            FunctionTool(fn)
            for fn in (
                giim_search_events,
                giim_get_event,
                giim_get_today_events,
                giim_get_coverage,
                giim_check_ready,
            )
        ]
