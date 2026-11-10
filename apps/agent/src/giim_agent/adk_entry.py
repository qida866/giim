"""ADK CLI/Web 安全外壳：只向外部会话发送最终门禁通过的响应。"""

import os
from contextlib import nullcontext
from pathlib import Path

from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.genai import types

from giim_mcp.config import Settings
from giim_mcp.demo import demo_api

from .config import pricing
from .logging import configure_logging
from .runtime import ask


class AnalystEntry(BaseAgent):
    async def _run_async_impl(self, ctx):
        configure_logging()
        question = " ".join(p.text for p in (ctx.user_content.parts or []) if p.text)
        live = os.getenv("GIIM_ADK_LIVE") == "1"
        demo = os.getenv("GIIM_ADK_DEMO", "1") == "1"
        try:
            if live and demo:
                raise ValueError("Live and demo modes are mutually exclusive")
            with demo_api() if demo else nullcontext(None) as fixture:
                settings = (
                    Settings(api_url=fixture[0], publisher_caps=fixture[1])
                    if fixture
                    else Settings.from_env()
                )
                answer = await ask(
                    question,
                    settings=settings,
                    live=live,
                    prices=pricing(),
                    trace_dir=Path(os.getenv("GIIM_TRACE_DIR", ".runs")),
                )
            text = answer.model_dump_json()
        except (ValueError, OSError):
            text = '{"status":"error","answer":"Invalid input or configuration.","claims":[]}'
        yield Event(
            author=self.name, content=types.Content(role="model", parts=[types.Part(text=text)])
        )


root_agent = AnalystEntry(name="giim_analyst")
