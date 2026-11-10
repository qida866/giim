"""Streamable HTTP 的 Host、Origin 和令牌保护。"""

import hmac

from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from .config import loopback
from .server import MCPServer


def create_http_app(
    server: MCPServer,
    host: str = "127.0.0.1",
    port: int = 8001,
    token: str | None = None,
    origins: tuple[str, ...] = (),
    public_host: str | None = None,
):
    if not loopback(host) and (not token or len(token) < 32):
        raise ValueError("Non-loopback HTTP requires a bearer token of at least 32 characters")
    if "*" in origins or any("*" in origin for origin in origins):
        raise ValueError("Wildcard origins are forbidden")
    allowed_host = public_host or host
    if not loopback(host) and allowed_host in ("0.0.0.0", "::"):
        raise ValueError("Non-loopback HTTP requires an explicit public Host")
    security = TransportSecuritySettings(
        allowed_hosts=[f"{allowed_host}:{port}"], allowed_origins=list(origins)
    )
    inner = server.streamable_http_app(
        host=host,
        stateless_http=True,
        json_response=True,
        max_request_body_size=32768,
        transport_security=security,
    )

    async def app(scope, receive, send):
        if scope["type"] != "http":
            return await inner(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        origin = headers.get("origin")
        if origin and origin not in origins:
            return await JSONResponse({"error": "forbidden_origin"}, status_code=403)(
                scope, receive, send
            )
        auth = headers.get("authorization", "")
        if token and not hmac.compare_digest(auth, "Bearer " + token):
            return await JSONResponse({"error": "unauthorized"}, status_code=401)(
                scope, receive, send
            )
        return await inner(scope, receive, send)

    return app
