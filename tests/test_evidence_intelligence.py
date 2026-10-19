"""来源独立性估计、重要性及逐项支持性复核。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from src.services.evidence_coverage import evidence_coverage
from src.services.ranking import rank_event
from src.services.claim_verification import verify_claims, all_supported
from src.services.event_contract import EventDraft
from src.services.event_quality import validate_draft
from tests.test_event_intelligence import article


def test_two_editions_cannot_supply_common_facts():
    reports = [article(1, source="Same publisher"), article(2, source="Same publisher")]
    claim = {"text": "Specific facts were reported", "citations": [
        {"news_id": n.id, "quote": n.title} for n in reports]}
    raw = {"coherent": True, "reason": "same event", "title": "Specific event reported",
           "sentences": [claim], "common_facts": [claim]}
    draft = validate_draft(json.dumps(raw), reports)
    assert draft.sentences
    assert draft.common_facts == []


def test_wire_copies_count_publishers_separately_from_origins():
    reports = [article(1, source="A"), article(2, source="B"), article(3, source="C")]
    for n in reports[:2]:
        n.raw_metadata = {"byline": "Reuters", "publisher_country": "GB"}
    reports[2].raw_metadata = {"publisher_country": "UN"}
    coverage = evidence_coverage(reports)
    assert coverage["publishers"] == 3
    assert coverage["independent_evidence_groups"] == 2
    assert coverage["publisher_countries"] == ["GB"]


def test_ownership_and_long_identical_copies_are_not_independent():
    reports = [article(i, source=str(i)) for i in range(4)]
    reports[0].raw_metadata = reports[1].raw_metadata = {"ownership_group": "one-company"}
    reports[2].content = reports[3].content = "Identical wire reporting. " * 12
    assert evidence_coverage(reports)["independent_evidence_groups"] == 2


def test_major_two_source_event_outranks_thirty_minor_reports():
    major = [article(i, source=str(i)) for i in range(2)]
    minor = [article(i, source=str(i)) for i in range(30)]

    def importance(level: str) -> dict:
        return {
            "mode": "ai_joint_verified",
            "importance": level,
            "why_it_matters": {"text": "Evidence-supported impact"},
        }

    assert (
        rank_event(major, importance=importance("major"))[0]
        > rank_event(minor, importance=importance("minor"))[0]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["unsupported", "missing", "unrelated"])
async def test_grounding_rejects_unsupported_incomplete_or_unrelated_review(kind):
    draft = EventDraft(
        coherent=True,
        reason="same",
        title="An incident",
        sentences=[
            {
                "text": "Ten people affected",
                "citations": [
                    {"news_id": 1, "quote": "The original source reports specific facts."}
                ],
            }
        ],
    )
    verdict = {
        "index": 0,
        "verdict": "unsupported" if kind == "unsupported" else "supported",
        "supporting_news_ids": [99] if kind == "unrelated" else [1],
        "reason": "Check",
    }
    llm = SimpleNamespace(
        chat=AsyncMock(
            return_value=SimpleNamespace(
                content=json.dumps(
                    {"title_supported": True, "claims": [] if kind == "missing" else [verdict]}
                )
            )
        )
    )
    if kind == "unsupported":
        assert not all_supported(await verify_claims(llm, draft, [article(1)]))
    else:
        with pytest.raises(ValueError):
            await verify_claims(llm, draft, [article(1)])
    messages = llm.chat.call_args.args[0].messages
    assert messages[0].role == "system"
    assert "untrusted DATA" in messages[0].content
    assert messages[1].role == "user"
