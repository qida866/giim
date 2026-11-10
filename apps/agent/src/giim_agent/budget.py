"""不可由模型放宽的请求预算。"""

from dataclasses import dataclass

from .security import BudgetExceeded


@dataclass
class Limits:
    timeout: float = 60
    tool_rounds: int = 3
    detail_calls: int = 5
    tool_calls: int = 9
    model_calls: int = 10
    output_tokens: int = 2048
    token_upper_bound: int = 120000
    max_context_bytes: int = 65000

    def __post_init__(self) -> None:
        if not (
            0 < self.timeout <= 180
            and 1 <= self.tool_rounds <= 3
            and 1 <= self.detail_calls <= 5
            and 1 <= self.tool_calls <= 9
            and 1 <= self.model_calls <= 10
            and 128 <= self.output_tokens <= 2048
            and 1000 <= self.token_upper_bound <= 120000
            and 1000 <= self.max_context_bytes <= 65000
        ):
            raise ValueError("Limits must stay within the supported hard bounds")


class Budget:
    def __init__(self, limits: Limits):
        self.limits = limits
        self.rounds = self.details = self.tools = self.models = self.reserved = 0

    def model(self, input_bytes: int) -> None:
        self.models += 1
        self.reserved += input_bytes + self.limits.output_tokens
        if (
            self.models > self.limits.model_calls
            or input_bytes > self.limits.max_context_bytes
            or self.reserved > self.limits.token_upper_bound
        ):
            raise BudgetExceeded("model_budget")

    def round(self) -> None:
        if self.rounds >= self.limits.tool_rounds:
            raise BudgetExceeded("tool_round_budget")
        self.rounds += 1

    def tool(self, name: str) -> None:
        if self.tools >= self.limits.tool_calls:
            raise BudgetExceeded("tool_call_budget")
        if name == "giim_get_event":
            if self.details >= self.limits.detail_calls:
                raise BudgetExceeded("event_detail_budget")
            self.details += 1
        self.tools += 1
