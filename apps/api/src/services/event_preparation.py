"""统一证据生成与支持性复核；不支持的输出退回原始报道。"""

from __future__ import annotations
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from src.models.news import News
from src.llm import LLMClient
from src.services.event_quality import (
    build_candidates,
    evidence_hash,
    select_evidence,
    generate_event,
    QUALITY_VERSION,
)
from src.services.claim_verification import verify_claims, all_supported
from src.services.story_review import membership_hash
from src.services.evidence_coverage import evidence_coverage, claim_status
from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PreparedEvent:
    news: list[News]
    title: str
    summary: str
    provenance: dict
    continuation_of: uuid.UUID | None = None


async def prepare_events(
    news: list[News],
    vectors: list[list[float]],
    llm: LLMClient | None,
    known: dict[str, dict],
    max_calls: int = 20,
    decisions: dict | None = None,
    excluded_ids: set[int] | None = None,
    candidate_groups: list[list[News]] | None = None,
    identity_reviewed: bool = False,
) -> tuple[list[PreparedEvent], dict]:
    now = datetime.now(timezone.utc)
    decisions = {
        k: v for k, v in (decisions or {}).items() if v.get("expires_at", "") > now.isoformat()
    }
    candidates = candidate_groups if candidate_groups is not None else build_candidates(news, vectors)
    candidates = [[n for n in group if n.id not in (excluded_ids or set())] for group in candidates]
    candidates = [group for group in candidates if group]
    queue = sorted(
        candidates,
        key=lambda g: (
            evidence_coverage(g)["independent_evidence_groups"] > 1,
            max(n.published_at for n in g),
        ),
        reverse=True,
    )
    prepared = []
    calls = 0
    rejected = 0
    grounding_rejected = 0
    fallbacks = 0
    while queue:
        group = queue.pop(0)
        digest = evidence_hash(group)
        if digest in known and (len(group) == 1 or (
            known[digest]["provenance"].get("identity_review")
            and known[digest]["provenance"].get("membership_hash") == membership_hash(group)
        )):
            old = known[digest]
            prepared.append(PreparedEvent(group, old["title"], old["summary"], old["provenance"]))
            continue
        draft = None
        review = None
        identity = None
        required = 4 if len(group) > 1 and not identity_reviewed else 2
        if digest not in decisions and llm is not None and calls + required <= max_calls:
            calls += 1
            try:
                if len(group) > 1 and not identity_reviewed:
                    from src.services.story_review import review_story
                    calls += 2
                    identity = await review_story(llm, group)
                    if not identity.accepted:
                        rejected += 1
                        decisions[digest] = {"outcome": "incoherent", "expires_at": (now + timedelta(hours=24)).isoformat()}
                        queue.extend([[n] for n in group])
                        continue
                draft = await generate_event(llm, group)
                if draft.coherent:
                    calls += 1
                    review = await verify_claims(llm, draft, select_evidence(group))
                    if not all_supported(review):
                        grounding_rejected += 1
                        draft = None
                        decisions[digest] = {
                            "outcome": "unsupported_generation",
                            "expires_at": (now + timedelta(hours=2)).isoformat(),
                        }
            except Exception as exc:
                draft = None
                decisions[digest] = {
                    "outcome": type(exc).__name__,
                    "expires_at": (now + timedelta(hours=1)).isoformat(),
                }
                logger.warning("event_generation_failed", error_type=type(exc).__name__)
        if draft is not None and not draft.coherent:
            rejected += 1
            decisions[digest] = {
                "outcome": "incoherent",
                "expires_at": (now + timedelta(hours=24)).isoformat(),
            }
            if len(group) > 1:
                queue.extend([[n] for n in group])
            continue
        if digest in decisions and decisions[digest]["outcome"] == "incoherent" and len(group) == 1:
            continue
        if draft is None and len(group) > 1:
            queue.extend([[n] for n in group])
            continue
        evidence = select_evidence(group)
        if draft:
            title = draft.title
            summary = "\n".join(s.text for s in draft.sentences)
            by_id = {n.id: n for n in evidence}
            sentences = [
                {
                    **s.model_dump(),
                    "fact_status": claim_status([by_id[c.news_id] for c in s.citations]),
                }
                for s in draft.sentences
            ]
            provenance = {
                "mode": "ai_joint_verified",
                "identity_review": identity.model_dump() if identity else None,
                "citations": sentences,
                "coherence": "model_reviewed",
                "grounding_review": review.model_dump(),
                "verification_scope": "LLM entailment review against selected excerpts; not independent fact verification",
                "category": draft.category,
                "importance": draft.importance if draft.why_it_matters else "unknown",
                "why_it_matters": draft.why_it_matters.model_dump()
                if draft.why_it_matters
                else None,
                "perspectives": {
                    "common_facts": [s.model_dump() for s in draft.common_facts],
                    "differences": [d.model_dump() for d in draft.differences],
                    "uncertainties": [s.model_dump() for s in draft.uncertainties],
                },
            }
        else:
            fallbacks += 1
            title = group[0].title
            summary = group[0].content[:500] or title
            provenance = {
                "mode": "source_excerpt",
                "citations": [],
                "coherence": "single_report_unreviewed",
                "category": "general",
                "importance": "unknown",
            }
        provenance.update(
            {
                "coverage": evidence_coverage(group),
                "evidence_ids": [n.id for n in evidence],
                "evidence_hash": digest,
                "model": getattr(llm, "_default_model", None) if draft else None,
                "generated_at": now.isoformat(),
                "quality_version": QUALITY_VERSION,
            }
        )
        prepared.append(PreparedEvent(group, title, summary, provenance))
    return prepared, {
        "llm_calls": calls,
        "rejected_candidates": rejected,
        "grounding_rejections": grounding_rejected,
        "source_fallbacks": fallbacks,
        "candidates": len(candidates),
        "decisions": decisions,
    }
