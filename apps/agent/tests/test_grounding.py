"""不依赖 LLM 的引用关联、历史和省略检测。"""

import copy
from uuid import UUID

import pytest
from pydantic import ValidationError

from giim_mcp.config import Settings
from giim_mcp.fixtures import CAPS, RECORDS, identifier
from giim_mcp.models import Listing
from giim_mcp.normalize import card, detail
from giim_agent.ledger import Ledger
from giim_agent.schemas import Draft, Verification


def fixture():
    ledger = Ledger()
    record = detail(copy.deepcopy(RECORDS[2]), UUID(identifier(3)), Settings(publisher_caps=CAPS))
    ledger.listing(Listing(events=[card(RECORDS[2]["event"])]))
    ledger.detail(record, False)
    draft = Draft(
        claims=[
            {
                "quote": s.excerpt,
                "citation": {
                    "event_id": s.event_id,
                    "article_id": s.article_id,
                    "publisher": s.publisher,
                    "url": s.url,
                },
            }
            for s in ledger.eligible().values()
        ]
    )
    return ledger, draft, record


def test_exact_current_quotes_and_unknown_cross_session():
    ledger, draft, _ = fixture()
    assert not ledger.validate(draft)
    assert "unknown_evidence_reference" in Ledger().validate(draft)
    draft.claims[0].quote = "The bridge remained closed."
    assert "unsupported_claim" in ledger.validate(draft)


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_id", UUID(identifier(1))),
        ("article_id", 390),
        ("publisher", "Invented"),
        ("url", "https://invented.example.org/"),
    ],
)
def test_wrong_association(field, value):
    ledger, draft, _ = fixture()
    setattr(draft.claims[0].citation, field, value)
    assert ledger.validate(draft)


def test_truncation_missing_publication_and_missing_citations():
    ledger, draft, record = fixture()
    ledger.detail(record, True)
    assert "incomplete_evidence" in ledger.validate(draft)
    ledger.blocked.clear()
    record.articles[0].published_at = None
    ledger.detail(record, False)
    assert ledger.validate(draft)
    assert "missing_evidence" in ledger.validate(Draft())


@pytest.mark.parametrize(
    "body",
    [{"ok": "true"}, {"ok": True, "extra": "ignore"}, {"ok": False, "missing_citations": "none"}],
)
def test_verifier_strict_schema(body):
    with pytest.raises(ValidationError):
        Verification.model_validate(body)


def test_missing_restricted_or_unverified_current_support_blocks_answer():
    ledger, draft, record = fixture()
    record.articles[0].excerpt = None
    ledger.detail(record, False)
    assert "withheld_or_incomplete_support" in ledger.validate(draft)
    ledger, draft, record = fixture()
    record.articles[0].time_quality = "unverified"
    ledger.detail(record, False)
    assert "withheld_or_incomplete_support" in ledger.validate(draft)
    ledger, draft, record = fixture()
    record.evidence_ids.append(999999)
    ledger.detail(record, False)
    assert "incomplete_current_support" in ledger.validate(draft)
