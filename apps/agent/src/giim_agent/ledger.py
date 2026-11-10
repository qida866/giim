"""仅从本次 MCP 详情建立可信证据关联；模型输出不能写入账本。"""

from uuid import UUID

from giim_mcp.models import Detail, Listing, Source

from .schemas import Draft
from .security import suspicious


class Ledger:
    def __init__(self) -> None:
        self.discovered: set[UUID] = set()
        self.details: dict[UUID, Detail] = {}
        self.blocked: set[str] = set()

    def listing(self, data: Listing) -> None:
        self.discovered.update(event.id for event in data.events)

    def detail(self, data: Detail, truncated: bool) -> None:
        if truncated or (
            data.total_articles is not None and data.total_articles > len(data.articles)
        ):
            self.blocked.add("incomplete_evidence")
        if data.status != "active":
            self.blocked.add("inactive_event")
        if data.event.id not in self.discovered:
            self.blocked.add("undiscovered_event")
            return
        current = [s for s in data.articles if s.current_support is True]
        seen = {s.article_id for s in current}
        if data.evidence_ids is None or seen != set(data.evidence_ids) or len(seen) != len(current):
            self.blocked.add("incomplete_current_support")
        for source in current:
            if not (
                source.url
                and source.publisher
                and source.published_at
                and source.excerpt
                and source.time_quality == "verified"
                and source.event_id == data.event.id
            ):
                self.blocked.add("withheld_or_incomplete_support")
        for source in data.articles:
            if source.current_support and suspicious(
                " ".join(filter(None, (source.excerpt, source.publisher, source.title)))
            ):
                self.blocked.add("untrusted_instructions")
        self.details[data.event.id] = data.model_copy(deep=True)

    def eligible(self) -> dict[tuple[UUID, int], Source]:
        return {
            (event_id, source.article_id): source
            for event_id, detail in self.details.items()
            for source in detail.articles
            if source.current_support is True
            and source.time_quality == "verified"
            and source.excerpt
            and source.publisher
            and source.url
            and source.published_at
        }

    def evidence(self) -> list[dict]:
        return [source.model_dump(mode="json") for source in self.eligible().values()]

    def validate(self, draft: Draft) -> list[str]:
        errors = set(self.blocked)
        eligible = self.eligible()
        if not draft.claims or not eligible:
            errors.add("missing_evidence")
        cited = set()
        for claim in draft.claims:
            citation = claim.citation
            key = (citation.event_id, citation.article_id)
            source = eligible.get(key)
            if not source:
                errors.add("unknown_evidence_reference")
                continue
            cited.add(key)
            if citation.url != source.url or citation.publisher != source.publisher:
                errors.add("citation_association_mismatch")
            # 完整短摘录匹配，避免截取句子造成否定、时间或上下文反转。
            if claim.quote != source.excerpt or suspicious(claim.quote):
                errors.add("unsupported_claim")
        if len(cited) != len(draft.claims):
            errors.add("duplicate_or_invalid_citations")
        # 保留所有取回的当前证据，不能让模型静默删掉异议来源。
        if cited != set(eligible):
            errors.add("omitted_current_evidence")
        if len(eligible) > 1 and not draft.acknowledge_uncertainty:
            errors.add("missing_uncertainty")
        return sorted(errors)
