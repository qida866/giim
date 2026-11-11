"""每请求独立 ADK 会话、MCP 连接、预算与账本。"""

import asyncio
import json
import os
import sys
from pathlib import Path

from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from mcp import Client, StdioServerParameters

from giim_mcp.config import Settings

from .budget import Budget, Limits
from .coordinator import Coordinator
from .gateway import Gateway
from .hooks import Hooks
from .ledger import Ledger
from .roles import make_model, role_agent
from .retry import RetryingModel
from .schemas import Answer, Draft
from .security import BudgetExceeded, SafetyError, failure_category
from .trace import Trace


def stdio_target(settings: Settings) -> StdioServerParameters:
    # 不把模型密钥、数据库凭据或管理员令牌传给 MCP 子进程。
    env = {
        key: value
        for key, value in os.environ.items()
        if key in ("PATH", "PYTHONPATH", "SYSTEMROOT")
    }
    env.update(
        GIIM_API_URL=settings.api_url,
        GIIM_MCP_TIMEOUT=str(settings.timeout),
        GIIM_MCP_PUBLISHER_CAPS=json.dumps(settings.publisher_caps),
        GIIM_MCP_EXCERPT_LIMIT=str(settings.excerpt_limit),
    )
    return StdioServerParameters(command=sys.executable, args=["-m", "giim_mcp"], env=env)


def readable(draft: Draft) -> str:
    lines = [
        "Sources retrieved for this request report the following policy-limited excerpts. These reports "
        "may disagree; they do not establish independent confirmation or certainty."
    ]
    for claim in draft.claims:
        c = claim.citation
        lines.append(f"{claim.quote}\n[{c.event_id} | {c.publisher} | {c.url}]")
    return "\n\n".join(lines)


async def ask(
    question: str,
    *,
    settings: Settings | None = None,
    target=None,
    live: bool = False,
    model: str | None = None,
    limits: Limits | None = None,
    trace_dir: Path | None = Path(".runs"),
    prices: dict | None = None,
    faults: dict[str, str] | None = None,
    model_factory=make_model,
    evidence_sink: list[dict] | None = None,
) -> Answer:
    if not question.strip() or len(question) > 300:
        raise ValueError("Question must contain 1–300 non-whitespace characters")
    limits = limits or Limits()
    trace = Trace(question, "gemini" if live else "fake", trace_dir, prices)
    ledger, budget = Ledger(), Budget(limits)
    sessions = InMemorySessionService()
    session = await sessions.create_session(
        app_name="giim_analyst",
        user_id=trace.request_id,
        state={"question": question, "revisions": 0},
    )
    failure = None
    state = {}
    try:
        models = {
            role: model_factory(role, live, model, (faults or {}).get(role, "none"))
            for role in ("researcher", "writer", "verifier")
        }
        async with asyncio.timeout(limits.timeout):
            async with Client(
                target or stdio_target(settings or Settings.from_env()), read_timeout_seconds=25
            ) as client:
                await client.list_tools()
                gateway = Gateway(client, budget, ledger, trace)
                hooks = Hooks(budget, trace)
                roles = [
                    role_agent(
                        role,
                        RetryingModel(
                            model=models[role].model,
                            delegate=models[role],
                            role=role,
                            budget=budget,
                            trace=trace,
                        ),
                        hooks,
                        gateway.tools() if role == "researcher" else None,
                    )
                    for role in ("researcher", "writer", "verifier")
                ]
                root = Coordinator(name="coordinator", sub_agents=roles, ledger=ledger, trace=trace)
                runner = Runner(app_name="giim_analyst", agent=root, session_service=sessions)
                try:
                    async for _ in runner.run_async(
                        user_id=trace.request_id,
                        session_id=session.id,
                        new_message=types.Content(role="user", parts=[types.Part(text=question)]),
                        run_config=RunConfig(max_llm_calls=limits.model_calls),
                    ):
                        pass
                finally:
                    await runner.close()
    except TimeoutError:
        failure = "request_timeout"
    except (SafetyError, BudgetExceeded) as exc:
        failure = str(exc)
    except Exception as exc:
        trace.emit("failure", exception_type=type(exc).__name__)
        # 第三方异常可能携带请求正文或凭据，不直接输出或追踪。
        failure = failure_category(exc)
    final_session = await sessions.get_session(
        app_name="giim_analyst", user_id=trace.request_id, session_id=session.id
    )
    state = final_session.state if final_session else {}
    accepted = state.get("accepted") if not failure else None
    draft = Draft.model_validate(accepted) if accepted else None
    verified = bool(draft and not ledger.validate(draft))
    status = (
        "verified"
        if verified
        else (
            "error"
            if failure in ("execution_error", "request_timeout")
            else "insufficient_evidence"
        )
    )
    failure = failure or (
        None if verified else ",".join(state.get("errors") or ["missing_evidence"])
    )
    if evidence_sink is not None:
        evidence_sink.extend(ledger.evidence())
    summary = trace.finish(status, verified, state.get("revisions", 0), failure)
    summary.update(
        tool_rounds=budget.rounds,
        detail_calls=budget.details,
        conservative_token_reservation=budget.reserved,
    )
    return Answer(
        request_id=trace.request_id,
        status=status,
        verified=verified,
        answer=readable(draft)
        if verified
        else "The available GIIM evidence is insufficient "
        "to provide a verified answer. No unsupported claims or citations are returned.",
        claims=draft.claims if verified else [],
        revisions=state.get("revisions", 0),
        mode="gemini" if live else "fake",
        failure_category=failure,
        trace=summary,
    )
