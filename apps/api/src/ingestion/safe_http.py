"""限流体积与重定向，拒绝本机/私网地址；源配置仍须人工审阅。"""

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit
import httpx

MAX_BYTES = 4 * 1024 * 1024


async def validate_public_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Unsafe source URL")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("Source port must be HTTP(S)")
    addresses = await asyncio.get_running_loop().getaddrinfo(
        parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
    )
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("Source resolves to a non-public address")


async def get_public(
    client: httpx.AsyncClient, url: str, headers: dict | None = None
) -> httpx.Response:
    for _ in range(4):
        await validate_public_url(url)
        async with client.stream("GET", url, headers=headers or {}) as response:
            if response.has_redirect_location:
                url = urljoin(url, response.headers.get("location", ""))
                continue
            if response.status_code != 304:
                response.raise_for_status()
            chunks = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("Source response exceeds 4 MiB")
                chunks.append(chunk)
            return httpx.Response(
                response.status_code,
                headers={
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
                },
                content=b"".join(chunks),
                request=response.request,
            )
    raise ValueError("Too many source redirects")
