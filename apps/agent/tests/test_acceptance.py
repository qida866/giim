"""Independent acceptance regressions beyond empty-result fixture routing."""

import json
import pytest
from giim_mcp.adapter import Adapter
from giim_mcp.fixtures import RECORDS
from giim_mcp.models import Listing
from giim_mcp.normalize import card
from giim_mcp.rest import RestClient
from giim_mcp.server import create_server
from giim_agent.fake import FakeModel, response
from giim_agent.runtime import ask


class ForcedCandidates(Adapter):
    async def search(self, query, window, limit):
        # An approximate search can return unrelated but otherwise valid events.
        return Listing(events=[card(RECORDS[0]["event"])])


@pytest.mark.parametrize(
    "question",
    [
        "What will happen to the stock market exactly 100 years from now?",
        "When did the bridge reopen after the flood?",
    ],
)
async def test_fake_verifier_rejects_valid_but_irrelevant_search_results(settings, question):
    server = create_server(ForcedCandidates(RestClient(settings)))
    answer = await ask(question, settings=settings, target=server, trace_dir=None)
    assert answer.trace["tools"] == ["giim_search_events", "giim_get_event"]
    assert answer.status == "insufficient_evidence" and not answer.claims
    assert "verifier_rejected" in answer.failure_category and answer.revisions == 1


class DoubleCorruption(FakeModel):
    def draft(self, data):
        draft = json.loads(super().draft(data).content.parts[0].text)
        draft["claims"][0]["citation"].update(
            event_id="ffffffff-ffff-ffff-ffff-ffffffffffff",
            url="https://fabricated.example.org/no-evidence",
        )
        return response(draft)


async def test_fake_event_and_url_rejected_together_with_verifier_approval(settings):
    def factory(role, live, override, fault):
        return (
            DoubleCorruption(role=role)
            if role == "writer"
            else FakeModel(role=role, fault="approve_all" if role == "verifier" else "none")
        )

    answer = await ask("AI laboratory", settings=settings, trace_dir=None, model_factory=factory)
    assert not answer.verified and not answer.claims and answer.revisions == 1
    assert "unknown_evidence_reference" in answer.failure_category


async def test_fake_verifier_does_not_claim_to_validate_arbitrary_real_news(settings):
    source = {
        "event_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
        "article_id": 1,
        "publisher": "Authored test",
        "url": "https://demo.example.org/unknown",
        "excerpt": "A synthetic claim outside the fake model fixture world.",
    }
    result = FakeModel(role="verifier").verify(
        {
            "question": "AI laboratory",
            "evidence": [source],
            "draft": {
                "claims": [
                    {
                        "quote": source["excerpt"],
                        "citation": {
                            key: source[key]
                            for key in ("event_id", "article_id", "publisher", "url")
                        },
                    }
                ]
            },
        }
    )
    assert json.loads(result.content.parts[0].text)["ok"] is False
