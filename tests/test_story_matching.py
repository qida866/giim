"""候选不是合并；主动作审核、时序边界与所有成员证据约束。"""

from src.models.news import News

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import timedelta
import pytest
from src.services.story_matching import fragment_candidates
from src.services.story_review import membership_hash, validate_review, review_story
from tests.test_event_intelligence import article


def payload(news: list[News], relation: str='same_incident') -> dict:
    return {'relation': relation, 'identity': 'Specific occurrence', 'reason': 'Exact evidence',
            'anchors': [{'news_id':n.id, 'quote':n.title} for n in news]}


@pytest.mark.parametrize('language,delay', [('en', 1), ('ko', 12), ('ja', 80), ('ar', 144)])
def test_retrieval_allows_delayed_multilingual_candidates(language: str, delay: int) -> None:
    old, new = article(1, hours=delay), article(2)
    new.language = language
    result = fragment_candidates([[old], [new]], {1:[1,0],2:[.6,.8]})
    assert len(result) == 1
    assert old.id != new.id  # 仅返回索引，不修改成员或关系。


def test_retrieval_bounds_time_and_oversized_stories() -> None:
    old, new = article(1, hours=193), article(2)
    assert not fragment_candidates([[old],[new]], {1:[1,0],2:[1,0]})
    assert not fragment_candidates([[article(i) for i in range(24)],[article(30)]],
                                   {i:[1,0] for i in range(31)})


def test_all_members_change_cache_even_outside_summary_sample() -> None:
    rows = [article(i, hours=i) for i in range(12)]
    before = membership_hash(rows)
    rows[-1].content += '  '
    assert membership_hash(rows) == before
    rows[-1].content += 'Correction: this was another incident.'
    assert membership_hash(rows) != before


def test_identity_requires_every_member_and_actual_quotes() -> None:
    rows = [article(1), article(2)]
    p = payload(rows); p['anchors'].pop()
    with pytest.raises(ValueError, match='every report'):
        validate_review(json.dumps(p), rows)
    p = payload(rows); p['anchors'][1]['quote'] = 'Fabricated anchor'
    with pytest.raises(ValueError, match='Invalid identity'):
        validate_review(json.dumps(p), rows)


def test_same_place_earthquakes_have_distinct_instrument_identity() -> None:
    rows=[article(1, 'M5 earthquake Japan'), article(2,'M5 earthquake Japan')]
    for n in rows:
        n.raw_metadata={'publisher_id':'usgs'}
    with pytest.raises(ValueError, match='Different official earthquake'):
        validate_review(json.dumps(payload(rows)), rows)


@pytest.mark.asyncio
@pytest.mark.parametrize('subject', ['same actor different meeting','same company different announcement',
    'same country different disaster','reaction versus original lawsuit','same conflict separate attacks'])
async def test_primary_action_rejection_overrides_positive_identity(subject: str) -> None:
    rows=[article(1,subject),article(2)]
    llm=SimpleNamespace(chat=AsyncMock(side_effect=[
        SimpleNamespace(content=json.dumps(payload(rows))),
        SimpleNamespace(content=json.dumps({'compatible':False,'reason':'Different primary actions','title_anchors':[]}))]))
    assert not (await review_story(llm,rows)).accepted
    assert llm.chat.call_count==2
    assert llm.chat.call_args_list[0].args[0].messages[0].role=='system'
    primary_input = json.loads(llm.chat.call_args_list[1].args[0].messages[1].content)
    assert all(set(row) == {'id', 'title'} for row in primary_input)


@pytest.mark.asyncio
async def test_ambiguous_identity_never_proceeds_to_secondary_review() -> None:
    rows=[article(1),article(2)]
    llm=SimpleNamespace(chat=AsyncMock(return_value=SimpleNamespace(content=json.dumps(payload(rows,'ambiguous')))))
    assert not (await review_story(llm,rows)).accepted
    assert llm.chat.call_count==1


@pytest.mark.asyncio
@pytest.mark.parametrize('families,actors,accepted',[
    (['arrest','arrest'],[['Person A'],['Person B']],False),
    (['arrest','release'],[['Person A'],['Person A']],True),
    (['military_support','military_support'],[['US','Saudi Arabia'],['UK','Saudi Arabia']],False),
    (['military_support','military_support'],[['UK','Saudi Arabia'],['UK','Ukraine']],False),
    (['meeting','diplomatic_statement'],[['A','B'],['A','B']],False),
    (['military_support','military_attack'],[['A'],['A']],False),
    (['roundup','roundup'],[['A'],['A']],False),
    (['analysis','analysis'],[['A'],['A']],False),
    (['other','other'],[['A'],['A']],False),
    (['election','military_attack'],[['A'],['A']],False),
    (['visit','letter'],[['A','B'],['A']],False),
    (['meeting','visit'],[['A','B'],['A','C']],False),
    (['visit','meeting'],[['A','B'],['B','A']],True),
    (['natural_disaster','natural_disaster'],[[],[]],True),
])
async def test_action_signatures_override_overbroad_model_acceptance(families: list[str], actors: list[list[str]], accepted: bool) -> None:
    rows=[article(1),article(2)]
    audit={'compatible':True,'reason':'same topic','title_anchors':payload(rows)['anchors'],
           'actions':[{'news_id':n.id,'family':f,'actors':a} for n,f,a in zip(rows,families,actors)]}
    llm=SimpleNamespace(chat=AsyncMock(side_effect=[SimpleNamespace(content=json.dumps(payload(rows))),
                                                  SimpleNamespace(content=json.dumps(audit))]))
    assert (await review_story(llm,rows)).accepted is accepted


def test_materially_revised_old_report_can_support_current_brief() -> None:
    from datetime import datetime, timezone
    from src.services.event_quality import select_evidence
    rows=[article(i,source=str(i),hours=i) for i in range(12)]
    original_time=rows[-1].published_at
    rows[-1].raw_metadata={'last_observed_revision_at':datetime.now(timezone.utc).isoformat()}
    assert rows[-1] in select_evidence(rows)
    assert rows[-1].published_at==original_time


@pytest.mark.asyncio
async def test_old_matching_version_cannot_reuse_multireport_ai_summary() -> None:
    from src.services.event_preparation import prepare_events
    from src.services.event_quality import evidence_hash
    rows = [article(1), article(2)]
    known = {evidence_hash(rows): {'title': 'Old AI title', 'summary': 'Old AI claim',
        'provenance': {'mode': 'ai_joint_verified', 'identity_review': {'relation': 'same_incident'},
                       'membership_hash': 'obsolete_matching_version'}}}
    prepared, _ = await prepare_events(rows, [[1, 0], [1, 0]], None, known,
                                      candidate_groups=[rows])
    assert len(prepared) == 2
    assert all(p.provenance['mode'] == 'source_excerpt' for p in prepared)
    assert all(p.summary != 'Old AI claim' for p in prepared)
