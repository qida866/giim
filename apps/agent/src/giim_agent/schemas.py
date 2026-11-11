"""研究、草稿、审查与最终响应契约。"""

from typing import Annotated, Literal
from uuid import UUID
from giim_mcp.models import ArticleID

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema, field_serializer


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResearchBundle(StrictModel):
    event_ids: list[UUID] = Field(default_factory=list, max_length=5)
    insufficient: bool = False
    contradictions: bool = False
    notes: str = Field(default="", max_length=1000)

    @field_serializer("event_ids")
    def serialize_event_ids(self, values: list[UUID]) -> list[str]:
        # ADK's terminal response tool uses model_dump() then json.dumps().
        # Keep UUID validation/internal values while making that boundary JSON-safe.
        return [str(value) for value in values]


class Citation(StrictModel):
    event_id: UUID
    # Google GenAI rejects exclusiveMinimum; minimum=1 is equivalent for strict integers.
    article_id: Annotated[ArticleID, WithJsonSchema({"type": "integer", "minimum": 1})]
    publisher: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)

    @field_serializer("event_id")
    def serialize_event_id(self, value: UUID) -> str:
        return str(value)


class Claim(StrictModel):
    quote: str = Field(min_length=1, max_length=500)
    citation: Citation


class Draft(StrictModel):
    claims: list[Claim] = Field(default_factory=list, max_length=30)
    acknowledge_uncertainty: bool = Field(
        default=True,
        description=(
            "Must be true when more than one current source is supplied, including agreeing "
            "reports and translations. Acknowledges evidence limitations, not only contradictions. "
            "Set true to repair missing_uncertainty."
        ),
    )


class Verification(StrictModel):
    ok: bool = Field(strict=True)
    unsupported_claims: list[str] = Field(default_factory=list, max_length=30)
    missing_citations: list[str] = Field(default_factory=list, max_length=30)


class Answer(StrictModel):
    request_id: str
    status: Literal["verified", "insufficient_evidence", "error"]
    answer: str
    claims: list[Claim] = Field(default_factory=list)
    verified: bool = False
    revisions: int = 0
    mode: Literal["fake", "gemini"]
    failure_category: str | None = None
    trace: dict = Field(default_factory=dict)
