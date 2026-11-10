"""环境配置及 URL 安全边界。"""

import ipaddress
import json
import os
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


def loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def safe_url(value: str | None) -> str | None:
    if not value or any(ord(c) < 33 for c in value):
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return None
        if parts.username or parts.password or parts.fragment:
            return None
        # 签名 URL 及查询中的凭据不进入模型上下文。
        if parts.query:
            return None
        _ = parts.port
        return value
    except ValueError:
        return None


class Settings(BaseModel):
    api_url: str = "http://127.0.0.1:8000"
    timeout: float = Field(default=10, gt=0, le=60)
    excerpt_limit: int = Field(default=500, ge=0, le=500)
    publisher_caps: dict[str, int] = Field(default_factory=dict)
    max_bytes: int = Field(default=20000, ge=2048, le=20000)
    upstream_bytes: int = Field(default=1000000, ge=20000, le=2000000)

    @field_validator("api_url")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        clean = safe_url(value)
        if not clean:
            raise ValueError("GIIM API must be a credential-free HTTP(S) origin")
        parts = urlsplit(clean)
        if parts.path not in ("", "/"):
            raise ValueError("GIIM API URL must be an origin without a path")
        if parts.scheme != "https" and not loopback(parts.hostname or ""):
            raise ValueError("Remote GIIM API requires HTTPS")
        return value.rstrip("/")

    @field_validator("publisher_caps")
    @classmethod
    def validate_caps(cls, value: dict[str, int]) -> dict[str, int]:
        if len(value) > 100 or any(cap < 0 or cap > 500 for cap in value.values()):
            raise ValueError("Publisher excerpt caps must be between zero and 500")
        return value

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_url=os.getenv("GIIM_API_URL", "http://127.0.0.1:8000"),
            timeout=os.getenv("GIIM_MCP_TIMEOUT", "10"),
            excerpt_limit=os.getenv("GIIM_MCP_EXCERPT_LIMIT", "500"),
            publisher_caps=json.loads(os.getenv("GIIM_MCP_PUBLISHER_CAPS", "{}")),
        )
