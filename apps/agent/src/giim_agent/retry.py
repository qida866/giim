"""Explicit provider retries; every extra attempt consumes the existing workflow budget."""

import asyncio
import json
import random
from time import perf_counter

import aiohttp
import httpx
import httpx2
from google.adk.models.base_llm import BaseLlm
from google.genai import types
from google.genai.errors import APIError
from pydantic import BaseModel, ConfigDict

from .budget import Budget
from .security import SafetyError
from .trace import Trace

TRANSIENT = frozenset({408, 429, 500, 502, 503, 504})


def transient(exc):
    return (isinstance(exc, APIError) and exc.code in TRANSIENT) or isinstance(
        exc,
        (httpx.TransportError, httpx2.TransportError, aiohttp.ClientConnectionError, TimeoutError),
    )


def retry_delay(retry_index):
    # Equal jitter: retain exponential growth while avoiding synchronized clients.
    ceiling = min(4.0, 0.5 * 2**retry_index)
    return random.uniform(ceiling / 2, ceiling)


class RetryingModel(BaseLlm):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    delegate: BaseLlm
    role: str
    budget: Budget
    trace: Trace

    async def generate_content_async(self, llm_request, stream=False):
        if stream:
            raise SafetyError("provider_streaming_not_supported")
        # Disable per-request SDK retries too: there must be only one retry owner.
        options = llm_request.config.http_options or types.HttpOptions(timeout=20000)
        llm_request.config.http_options = options.model_copy(
            update={"retry_options": types.HttpRetryOptions(attempts=1)}
        )

        def encode(value):
            return (
                value.model_json_schema()
                if isinstance(value, type) and issubclass(value, BaseModel)
                else str(value)
            )

        size = len(json.dumps(llm_request.model_dump(exclude_none=True), default=encode).encode())
        for attempt in range(1, self.budget.limits.provider_retries + 2):
            if attempt > 1:
                # The first attempt is reserved by Hooks.before. Extra attempts share
                # exactly that request's call/token limits; TrialModel also reserves $.
                try:
                    self.budget.model(size)
                except SafetyError:
                    self.trace.emit("provider_retry_stopped", role=self.role, reason="model_budget")
                    raise
                self.trace.emit("model_start", role=self.role, model=self.model, retry=attempt - 1)
                self.trace.emit("provider_retry", role=self.role, attempt=attempt)
            started, yielded = perf_counter(), False
            try:
                async for response in self.delegate.generate_content_async(
                    llm_request, stream=False
                ):
                    yielded = True
                    if attempt > 1:
                        self.trace.emit("provider_recovered", role=self.role, attempt=attempt)
                    yield response
                return
            except asyncio.CancelledError:
                self.trace.emit("provider_cancelled", role=self.role, attempt=attempt)
                raise
            except SafetyError:
                self.trace.emit("provider_retry_stopped", role=self.role, reason="safety_or_budget")
                raise
            except Exception as exc:
                # Never record provider messages, request bodies, headers or raw URLs.
                retryable = transient(exc) and not yielded
                status = (
                    exc.code if isinstance(exc, APIError) and isinstance(exc.code, int) else None
                )
                self.trace.emit(
                    "provider_error",
                    role=self.role,
                    attempt=attempt,
                    exception_type=type(exc).__name__,
                    http_status=status,
                    transient=retryable,
                    partial_response=yielded,
                    latency_seconds=perf_counter() - started,
                )
                if not retryable or attempt > self.budget.limits.provider_retries:
                    self.trace.emit(
                        "provider_retry_stopped",
                        role=self.role,
                        reason="exhausted" if retryable else "non_retryable",
                    )
                    raise
                # Don't wait if the next attempt cannot fit the request budget.
                try:
                    self.budget.check_model(size)
                except SafetyError:
                    self.trace.emit("provider_retry_stopped", role=self.role, reason="model_budget")
                    raise
                delay = retry_delay(attempt - 1)
                self.trace.emit(
                    "provider_retry_scheduled",
                    role=self.role,
                    next_attempt=attempt + 1,
                    delay_seconds=delay,
                )
                await asyncio.sleep(delay)
