"""在 SDK 的默认宽松参数处理之前执行严格输入校验。"""

from typing import Annotated
from uuid import UUID

from mcp.types import CallToolResult, TextContent
from pydantic import Field, ValidationError

from .models import Contract, Window


class TodayInput(Contract):
    window: Window = "24h"
    limit: Annotated[int, Field(strict=True, ge=1, le=25)] = 10
    language: Annotated[str | None, Field(min_length=2, max_length=20)] = None


class SearchInput(Contract):
    query: Annotated[str, Field(min_length=1, max_length=300)]
    window: Window | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=20)] = 10


class EventInput(Contract):
    event_id: UUID


INPUTS = {
    "giim_get_today_events": TodayInput,
    "giim_search_events": SearchInput,
    "giim_get_event": EventInput,
    "giim_get_coverage": Contract,
    "giim_check_ready": Contract,
}


async def strict_inputs(ctx, call_next):
    if ctx.method == "tools/call":
        params = ctx.params or {}
        schema = INPUTS.get(params.get("name"))
        if schema:
            try:
                schema.model_validate(params.get("arguments") or {})
            except (ValidationError, TypeError):
                return CallToolResult(
                    is_error=True,
                    content=[
                        TextContent(
                            type="text",
                            text="invalid_request: arguments do not match the tool schema",
                        )
                    ],
                )
    result = await call_next(ctx)
    if isinstance(result, CallToolResult) and result.structured_content is not None:
        # 避免 SDK 同时输出两份正文，让整个响应保持约 20 KB 上限。
        result.content = [TextContent(type="text", text="GIIM result is in structuredContent.")]
    return result
