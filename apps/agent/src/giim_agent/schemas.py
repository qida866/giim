"""研究、草稿、审查与最终响应契约。"""

from typing import Literal
from uuid import UUID
from giim_mcp.models import ArticleID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResearchBundle(StrictModel):
    event_ids: list[UUID] = Field(default_factory=list, max_length=5)
    insufficient: bool = False
    contradictions: bool = False
    notes: str = Field(default="", max_length=1000)


class Citation(StrictModel):
    event_id: UUID
    article_id: ArticleID
    publisher: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)


class Claim(StrictModel):
    quote: str = Field(min_length=1, max_length=500)
    citation: Citation


class Draft(StrictModel):
    claims: list[Claim] = Field(default_factory=list, max_length=30)
    acknowledge_uncertainty: bool = True


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
