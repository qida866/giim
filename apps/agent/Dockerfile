FROM python:3.11.15-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/agent/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r /app/requirements.lock \
    && useradd --uid 10001 --create-home analyst
COPY apps/mcp_server /app/apps/mcp_server
COPY apps/agent /app/apps/agent
COPY scripts/summarize_runs.py scripts/sample_agent_evals.py /app/scripts/
RUN pip install --no-cache-dir --no-build-isolation --no-deps /app/apps/mcp_server /app/apps/agent \
    && pip check && mkdir -p /app/.runs && chown -R analyst:analyst /app
USER analyst
ENTRYPOINT ["python", "-m", "giim_agent"]
CMD ["ask", "What happened at the AI laboratory?", "--demo"]
