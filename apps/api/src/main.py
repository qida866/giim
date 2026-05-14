"""GIIM API 应用入口，负责组装 FastAPI 组件。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.exceptions import register_exception_handlers
from src.core.lifespan import lifespan
from src.routers.health import router as health_router
from src.routers.ingestion import router as ingestion_router
from src.routers.news import router as news_router
from src.routers.search import router as search_router

app = FastAPI(title="GIIM API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(news_router, prefix="/api/v1", tags=["news"])
app.include_router(search_router, prefix="/api/v1", tags=["search"])
app.include_router(ingestion_router, prefix="/api/v1")
