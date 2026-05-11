FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# torch CPU 版 (避免拉 NVIDIA CUDA 依赖,节省 2GB+)
RUN uv pip install --system \
    --index-url https://download.pytorch.org/whl/cpu \
    torch>=2.0.0

RUN uv pip install --system \
    fastapi \
    "uvicorn[standard]" \
    "sqlalchemy[asyncio]" \
    asyncpg \
    alembic \
    pydantic \
    pydantic-settings \
    qdrant-client \
    structlog \
    httpx \
    python-dotenv \
    pytest \
    pytest-asyncio \
    pytest-cov \
    ruff \
    mypy \
    feedparser \
    beautifulsoup4 \
    python-dateutil \
    openai \
    sentence-transformers>=3.0.0

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends wget \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local /usr/local
COPY apps/api/src /app/src

HEALTHCHECK --interval=10s --timeout=5s --retries=10 CMD wget -qO- http://localhost:8000/api/v1/health > /dev/null || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
