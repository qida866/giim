"""固定路由只读客户端；错误不包含响应正文或认证信息。"""

import asyncio
import random
import re
from typing import Any

import httpx

from .config import Settings
from .models import ToolError


class AdapterError(Exception):
    def __init__(self, code: str, retryable: bool = False):
        self.error = ToolError(code=code, message=code.replace("_", " "), retryable=retryable)
        super().__init__(code)


class RestClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client or httpx.AsyncClient(
            timeout=settings.timeout, follow_redirects=False, trust_env=False
        )

    async def close(self) -> None:
        await self.client.aclose()

    @staticmethod
    def allowed(method: str, path: str) -> bool:
        return (method, path) in {
            ("GET", "/api/v1/events/today"),
            ("POST", "/api/v1/search/events"),
            ("GET", "/api/v1/coverage"),
            ("GET", "/api/v1/ready"),
        } or (method == "GET" and bool(re.fullmatch(r"/api/v1/events/[0-9a-fA-F-]{36}", path)))

    async def request(self, method: str, path: str, **kwargs: Any) -> dict | list:
        if not self.allowed(method, path):
            raise AdapterError("invalid_request")
        for attempt in range(2):
            try:
                return await self._once(method, path, **kwargs)
            except AdapterError as exc:
                if not exc.error.retryable or attempt:
                    raise
                await asyncio.sleep(random.uniform(0.02, 0.12))
        raise AdapterError("unavailable")

    async def _once(self, method: str, path: str, **kwargs: Any) -> dict | list:
        try:
            async with self.client.stream(
                method, self.settings.api_url + path, timeout=self.settings.timeout, **kwargs
            ) as response:
                status = response.status_code
                if status not in (200, 503) or (status == 503 and path != "/api/v1/ready"):
                    code = {404: "not_found", 422: "invalid_request", 429: "rate_limited"}.get(
                        status, "unavailable"
                    )
                    raise AdapterError(code, status in (429, 502, 503, 504))
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > self.settings.upstream_bytes:
                        raise AdapterError("response_too_large")
                import json

                result = json.loads(chunks)
                if not isinstance(result, (dict, list)):
                    raise AdapterError("malformed_response")
                return result
        except httpx.TimeoutException:
            raise AdapterError("timeout", True) from None
        except httpx.RequestError:
            raise AdapterError("unavailable", True) from None
        except (ValueError, UnicodeError):
            raise AdapterError("malformed_response") from None
