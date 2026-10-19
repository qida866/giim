FROM python:3.11.15-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/apps/api \
    EMBEDDING_MODEL_NAME=BAAI/bge-m3 EMBEDDING_CACHE_DIR=/app/.cache/huggingface EMBEDDING_DEVICE=cpu
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.lock \
    && useradd --uid 10001 --create-home giim \
    && mkdir -p /app/.cache/huggingface && chown -R giim:giim /app
COPY --chown=giim:giim apps/api/src /app/apps/api/src
COPY --chown=giim:giim scripts /app/scripts
COPY --chown=giim:giim alembic /app/alembic
COPY --chown=giim:giim frontend /app/frontend
COPY --chown=giim:giim tests /app/tests
COPY --chown=giim:giim evaluation /app/evaluation
COPY --chown=giim:giim config /app/config
COPY --chown=giim:giim alembic.ini pyproject.toml README.md /app/
USER giim
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health',timeout=3)"
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
