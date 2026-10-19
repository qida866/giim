"""标题、摘要、解释与视角共享同一证据契约。"""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    news_id: int
    quote: str = Field(min_length=5, max_length=800)


class Sentence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=5, max_length=500)
    citations: list[Citation] = Field(min_length=1, max_length=8)


class Comparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["different_emphasis", "different_reported_detail"]
    reporting: list[Sentence] = Field(min_length=2, max_length=3)


class EventDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coherent: bool
    reason: str = Field(max_length=500)
    title: str = Field(min_length=5, max_length=300)
    sentences: list[Sentence] = Field(min_length=1, max_length=3)
    category: Literal[
        "geopolitics",
        "conflict",
        "policy",
        "economy",
        "business",
        "technology",
        "ai",
        "science",
        "disasters",
        "weather",
        "public_safety",
        "health",
        "energy",
        "culture",
        "general",
    ] = "general"
    importance: Literal["unknown", "minor", "substantial", "major"] = "unknown"
    why_it_matters: Sentence | None = None
    common_facts: list[Sentence] = Field(default_factory=list, max_length=2)
    differences: list[Comparison] = Field(default_factory=list, max_length=2)
    uncertainties: list[Sentence] = Field(default_factory=list, max_length=2)


def all_claims(draft: EventDraft) -> list[Sentence]:
    return (
        draft.sentences
        + ([draft.why_it_matters] if draft.why_it_matters else [])
        + draft.common_facts
        + draft.uncertainties
        + [s for d in draft.differences for s in d.reporting]
    )
