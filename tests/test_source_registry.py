"""源身份、网络边界、健康和更新行为回归。"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import httpx
import pytest
from sqlalchemy import select
from src.ingestion.registry import load_registry
from src.ingestion.safe_http import validate_public_url, get_public, MAX_BYTES
from src.ingestion.rss_fetcher import fetch_rss, parse_feed, RssSource, ParsedNewsItem
from src.ingestion.orchestrator_schema import SourceRunStats
from src.ingestion.source_health import health_value
from src.ingestion.deduplicator import deduplicate_and_insert
from src.ingestion.usgs import parse_usgs
from src.models.news import News
from src.services.coverage import source_health_label


def test_language_editions_share_publisher_identity() -> None:
    sources=load_registry()
    dw=[s for s in sources if s.source_id.startswith('dw-')]
    assert len(dw)>=5 and len({s.publisher_id for s in dw})==1
    assert not any(s.source_id in {'nhk','who'} for s in sources)


def test_registry_duplicate_ids_fail_closed(tmp_path,monkeypatch) -> None:
    row={'source_id':'x','name':'Example','url':'https://example.com/rss','language':'en'}
    path=tmp_path/'registry.json';path.write_text(json.dumps({'sources':[row,row]}))
    monkeypatch.setenv('SOURCE_REGISTRY_PATH',str(path))
    with pytest.raises(ValueError,match='unique'):load_registry()


@pytest.mark.asyncio
@pytest.mark.parametrize('url',['http://127.0.0.1/','http://169.254.169.254/latest/','http://[::1]/','http://user:pass@example.com/','file:///etc/passwd'])
async def test_source_url_blocks_private_and_credential_addresses(url: str) -> None:
    with pytest.raises(ValueError):await validate_public_url(url)


@pytest.mark.asyncio
async def test_response_size_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr('src.ingestion.safe_http.validate_public_url',AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'x'*(MAX_BYTES+1)))) as client:
        with pytest.raises(ValueError,match='4 MiB'):await get_public(client,'https://example.com/feed')


@pytest.mark.asyncio
async def test_redirect_is_revalidated(monkeypatch) -> None:
    check=AsyncMock(side_effect=[None,ValueError('private')])
    monkeypatch.setattr('src.ingestion.safe_http.validate_public_url',check)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(302,headers={'location':'http://127.0.0.1/'}))) as client:
        with pytest.raises(ValueError):await get_public(client,'https://example.com/feed')
    assert check.await_args_list[-1].args==('http://127.0.0.1/',)


@pytest.mark.asyncio
async def test_304_is_success_without_duplicate_parse(monkeypatch) -> None:
    request=httpx.Request('GET','https://example.com/rss')
    monkeypatch.setattr('src.ingestion.rss_fetcher.get_public',AsyncMock(return_value=httpx.Response(304,request=request)))
    result=await fetch_rss(RssSource(name='A',url=str(request.url),language='en'))
    assert result.success and result.not_modified and result.items==[]


@pytest.mark.asyncio
async def test_http_wrapper_does_not_follow_304_as_redirect(monkeypatch) -> None:
    check = AsyncMock()
    monkeypatch.setattr('src.ingestion.safe_http.validate_public_url', check)
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(304, headers={'etag': 'unchanged'})
    )) as client:
        response = await get_public(client, 'https://example.com/rss')
    assert response.status_code == 304
    assert response.headers['etag'] == 'unchanged'
    check.assert_awaited_once()


def test_health_preserves_failure_and_success_independently() -> None:
    now=datetime.now(timezone.utc)
    good=health_value({},SourceRunStats(source_name='A',success=True,latest_published_at=now),now)
    failed=health_value(good,SourceRunStats(source_name='A',success=False,fetch_error='ReadTimeout'),now+timedelta(minutes=30))
    assert failed['last_success']==good['last_success'] and failed['last_failure']
    assert source_health_label(failed,now)=='failing'
    recovered=health_value(failed,SourceRunStats(source_name='A',success=True,not_modified=True),now+timedelta(minutes=40))
    assert recovered['last_failure']==failed['last_failure'] and recovered['latest_published_at']==good['latest_published_at']


@pytest.mark.asyncio
async def test_same_url_revision_preserves_publication_and_history(db_session) -> None:
    now=datetime.now(timezone.utc)
    item=ParsedNewsItem(source_name='Revision test',source_url='https://example.test/revision',title='One specific incident',content='Initial reporting',language='en',published_at=now,metadata={'publisher_id':'revision'})
    await deduplicate_and_insert([item],db_session)
    result=await deduplicate_and_insert([item.model_copy(update={'content':'Updated reporting with new evidence'})],db_session)
    assert result.updated==1 and result.inserted==0
    news=await db_session.scalar(select(News).where(News.source_url==item.source_url))
    assert news.published_at==now and news.raw_metadata['revisions'][0]['content']=='Initial reporting'


def test_usgs_keeps_occurrence_and_record_update_distinct() -> None:
    now=datetime.now(timezone.utc)
    data={'type':'FeatureCollection','features':[{'id':'quake1','properties':{'title':'M 5.1 - Test location','time':int((now-timedelta(hours=2)).timestamp()*1000),'updated':int(now.timestamp()*1000),'url':'https://earthquake.usgs.gov/earthquakes/eventpage/quake1','mag':5.1}}]}
    parsed=parse_usgs(data,RssSource(name='USGS',url='https://earthquake.usgs.gov/feed',language='en',role='official'),now)
    assert parsed.items[0].metadata['occurred_at']!=parsed.items[0].published_at.isoformat()
    assert parsed.items[0].metadata['timestamp_semantics']=='record_updated_at'


@pytest.mark.asyncio
async def test_operations_protected_and_public_coverage_sanitized(async_client_db) -> None:
    assert (await async_client_db.get('/api/v1/admin/operations')).status_code==403
    response=await async_client_db.get('/api/v1/coverage')
    assert response.status_code==200
    assert all('operation' not in s and 'config' not in s for s in response.json()['sources'])


@pytest.mark.asyncio
async def test_compressed_feed_is_decoded_once(monkeypatch) -> None:
    import gzip
    monkeypatch.setattr('src.ingestion.safe_http.validate_public_url',AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=gzip.compress(b'<rss/>'),headers={'Content-Encoding':'gzip'}))) as client:
        response=await get_public(client,'https://example.com/feed')
    assert response.text=='<rss/>'


def test_changed_feed_url_does_not_reuse_old_http_validators() -> None:
    from datetime import datetime, timezone
    from src.ingestion.source_health import health_value
    from src.ingestion.orchestrator_schema import SourceRunStats
    old={'fetch_url':'https://example.test/day','etag':'old-day','last_modified':'old-date'}
    result=SourceRunStats(source_name='USGS',fetch_url='https://example.test/week',success=True)
    value=health_value(old,result,datetime.now(timezone.utc))
    assert value['etag'] is None
    assert value['last_modified'] is None
