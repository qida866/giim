"""CLI 的第三方日志也经过密钥去敏；不输出异常正文。"""

import logging

from .security import environment_secrets, redact


class PrivateLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage(), environment_secrets())
        record.args = ()
        if record.exc_info:
            record.msg += " [exception details withheld]"
            record.exc_info = None
            record.exc_text = None
        return True


def configure_logging() -> None:
    logging.basicConfig(level=logging.ERROR)
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, PrivateLogFilter) for f in handler.filters):
            handler.addFilter(PrivateLogFilter())
