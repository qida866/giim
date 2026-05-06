"""异常模块，定义业务异常与全局异常处理。"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class GIIMException(Exception):
    """GIIM 业务异常基类。"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        detail: Any | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class DatabaseError(GIIMException):
    """数据库相关异常。"""

    def __init__(self, message: str, detail: Any | None = None) -> None:
        super().__init__(code="DATABASE_ERROR", message=message, status_code=500, detail=detail)


class VectorStoreError(GIIMException):
    """向量存储相关异常。"""

    def __init__(self, message: str, detail: Any | None = None) -> None:
        super().__init__(code="VECTOR_STORE_ERROR", message=message, status_code=500, detail=detail)


class LLMError(GIIMException):
    """LLM 调用相关异常。"""

    def __init__(self, message: str, detail: Any | None = None) -> None:
        super().__init__(code="LLM_ERROR", message=message, status_code=502, detail=detail)


class IngestionError(GIIMException):
    """数据采集相关异常。"""

    def __init__(self, message: str, detail: Any | None = None) -> None:
        super().__init__(code="INGESTION_ERROR", message=message, status_code=500, detail=detail)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。"""

    @app.exception_handler(GIIMException)
    async def handle_giim_exception(_: Request, exc: GIIMException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "detail": exc.detail},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_ERROR", "message": "服务器内部错误", "detail": str(exc)},
        )
