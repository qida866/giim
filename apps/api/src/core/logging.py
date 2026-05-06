"""日志模块，负责 structlog 的统一配置与获取。"""

import logging
import sys
from typing import Any

import structlog

from src.core.config import settings

_configured: bool = False


def _shared_processors() -> list[Any]:
    """返回开发与生产共用的处理器链。"""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]


def configure_logging() -> None:
    """根据环境配置日志输出格式。"""
    global _configured
    if _configured:
        return

    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    is_dev = settings.app_env.lower() == "dev"
    renderer = (
        structlog.dev.ConsoleRenderer(colors=True)
        if is_dev
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[
            *_shared_processors(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str) -> structlog.types.FilteringBoundLogger:
    """获取指定名称的日志实例。"""
    configure_logging()
    return structlog.get_logger(name)


configure_logging()
