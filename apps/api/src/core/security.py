"""单实例公共 API 限流与请求边界；不记录请求凭据。"""

from collections import defaultdict, deque
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class PublicLimits(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.requests = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        now = time.monotonic()
        if len(self.requests) > 10000:
            self.requests = {k: v for k, v in self.requests.items() if v and v[-1] > now - 60}
            self.requests = defaultdict(deque, self.requests)
        host = request.client.host if request.client else "unknown"
        expensive = request.url.path.rstrip("/").endswith(("/search", "/search/events"))
        key = (host, "search" if expensive else "general")
        bucket = self.requests[key]
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= (12 if expensive else 240):
            return JSONResponse(
                {"detail": "Too many requests; retry shortly"}, 429, headers={"Retry-After": "60"}
            )
        bucket.append(now)
        if request.method in ("POST", "PUT", "PATCH"):
            chunks = []
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 32768:
                    return JSONResponse({"detail": "Request too large"}, 413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'"
        )
        return response
