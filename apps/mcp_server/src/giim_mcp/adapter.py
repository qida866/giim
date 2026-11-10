"""五个工具共用的适配与响应体积限制。"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from . import normalize
from .config import Settings
from .models import Detail, Envelope, HOURS, Listing, Window
from .rest import AdapterError, RestClient


def bounded(envelope: Envelope, cap: int) -> Envelope:
    def size() -> int:
        return len(envelope.model_dump_json().encode())

    if size() <= cap:
        return envelope
    envelope.truncated = True
    data = envelope.data
    # 只删完整数组元素；输出仍满足原有结构化契约。
    fields = ("articles", "revisions") if isinstance(data, Detail) else ("sources", "events")
    for field in fields:
        items = getattr(data, field, None)
        while items and size() > cap:
            items.pop()
    if size() > cap:
        return Envelope(ok=False, error=AdapterError("response_too_large").error, truncated=True)
    return envelope


class Adapter:
    def __init__(self, rest: RestClient):
        self.rest = rest
        self.settings: Settings = rest.settings

    async def guarded(self, call: Callable[[], Awaitable]) -> Envelope:
        try:
            return bounded(Envelope(data=await call()), self.settings.max_bytes)
        except AdapterError as exc:
            return Envelope(ok=False, error=exc.error)
        except (KeyError, TypeError, ValueError, AttributeError):
            return Envelope(ok=False, error=AdapterError("malformed_response").error)

    async def today(self, window: Window, limit: int, language: str | None) -> Listing:
        rows = await self.rest.request(
            "GET",
            "/api/v1/events/today",
            params={"hours": HOURS[window], "limit": 50 if language else limit},
        )
        events = [normalize.card(r) for r in rows["events"]]
        if language:
            events = [r for r in events if language in r.languages]
        return Listing(
            events=events[:limit],
            language_filter_scope=(
                "post-filter of at most 50 API events; not an exhaustive language search"
                if language
                else None
            ),
        )

    async def search(self, query: str, window: Window | None, limit: int) -> Listing:
        if not query.strip():
            raise AdapterError("invalid_request")
        row = await self.rest.request(
            "POST",
            "/api/v1/search/events",
            json={"query": query, "hours": HOURS[window or "7d"], "top_k": limit},
        )
        events = [normalize.card(r) for r in row["events"]][:limit]
        event_ids = {str(event.id) for event in events}
        sources = [
            normalize.source(r, UUID(e), self.settings)
            for r in row.get("reports", [])
            for e in r.get("event_ids", [])
            if e in event_ids
        ]
        return Listing(events=events, sources=sources, ranking_basis=row.get("ranking_basis"))

    async def event(self, event_id: UUID) -> Detail:
        row = await self.rest.request("GET", f"/api/v1/events/{event_id}", params={"limit": 100})
        return normalize.detail(row, event_id, self.settings)

    async def coverage(self):
        return normalize.coverage(await self.rest.request("GET", "/api/v1/coverage"))

    async def ready(self):
        return normalize.readiness(await self.rest.request("GET", "/api/v1/ready"))
