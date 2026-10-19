"""GIIM API 应用入口，负责组装 FastAPI 组件。"""

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from src.core.config import settings
from src.core.security import PublicLimits
from fastapi.middleware.cors import CORSMiddleware

from src.core.exceptions import register_exception_handlers
from src.core.lifespan import lifespan
from src.routers.operations import router as operations_router
from src.routers.event_detail import router as event_detail_router
from src.routers.events import router as events_router
from src.routers.health import router as health_router
from src.routers.ingestion import router as ingestion_router
from src.routers.news import router as news_router
from src.routers.event_search import router as event_search_router
from src.routers.search import router as search_router

app = FastAPI(title="GIIM API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[s.strip() for s in settings.cors_origins.split(",") if s.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(operations_router, prefix="/api/v1", tags=["operations"])
app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(news_router, prefix="/api/v1", tags=["news"])
app.include_router(events_router, prefix="/api/v1", tags=["events"])
app.include_router(event_detail_router, prefix="/api/v1", tags=["events"])
app.include_router(event_search_router, prefix="/api/v1", tags=["search"])
app.include_router(search_router, prefix="/api/v1", tags=["search"])
app.include_router(ingestion_router, prefix="/api/v1")

app.add_middleware(PublicLimits)
frontend = Path.cwd() / "frontend"
if not frontend.exists():
    frontend = Path("/app/frontend")
if frontend.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend)), name="assets")
    @app.get("/", include_in_schema=False)
    async def home():
        return FileResponse(frontend / "index.html")
