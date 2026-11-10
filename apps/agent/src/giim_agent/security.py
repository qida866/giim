"""输入隔离、保守注入识别和日志去敏；不把模式识别视为完整防御。"""

import os
import re

INJECTION = re.compile(
    r"ignore.{0,40}(?:previous|instructions)|system\s*prompt|api[ _-]?key|"
    r"execute.{0,30}(?:shell|command)|(?:reveal|print|export).{0,30}(?:secret|password)|"
    r"忽略.{0,20}指令|系统提示|泄露|(?i:BEGIN SYSTEM)",
    re.I | re.S,
)
SECRET = re.compile(
    r"(?i)(?:bearer\s+\S+|(?:api[_ -]?key|token|password|secret)\s*[:=]\s*[^\s,;]+|"
    r"(?:sk-|AIza)[A-Za-z0-9_-]{12,}|[a-z][a-z0-9+.-]*://[^\s/@]+:[^\s/@]+@[^\s]+)"
)


class SafetyError(Exception):
    """只携带稳定错误代码。"""


class BudgetExceeded(SafetyError):
    pass


def suspicious(text: str) -> bool:
    return bool(INJECTION.search(text) or SECRET.search(text))


def redact(value, secrets: tuple[str, ...] = ()):
    if isinstance(value, dict):
        return {
            k: (
                "[REDACTED]"
                if re.search(r"key|token|secret|password|authorization", k, re.I)
                and not k.endswith("_tokens")
                and k not in ("tokens_per_second", "conservative_token_reservation")
                else redact(v, secrets)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in sorted(secrets, key=len, reverse=True):
            if len(secret) >= 4:
                value = value.replace(secret, "[REDACTED]")
        return SECRET.sub("[REDACTED]", value)[:2000]
    return value


def environment_secrets() -> tuple[str, ...]:
    return tuple(
        value
        for key, value in os.environ.items()
        if re.search(r"key|token|secret|password|credential|database_url", key, re.I)
        and len(value) >= 4
    )


def failure_category(exc: BaseException) -> str:
    """解包 SDK TaskGroup 异常，但从不暴露第三方异常正文。"""
    if isinstance(exc, SafetyError):
        return str(exc)
    if isinstance(exc, TimeoutError):
        return "request_timeout"
    if isinstance(exc, BaseExceptionGroup):
        values = [failure_category(e) for e in exc.exceptions]
        return next((v for v in values if v != "execution_error"), "execution_error")
    return "execution_error"
