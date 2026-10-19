"""发布时间与跨源/有界去重的行为回归。"""
from datetime import datetime,timedelta,timezone
import pytest
from src.ingestion.rss_fetcher import _parse_published_at,parse_feed,RssSource,ParsedNewsItem
from src.ingestion.deduplicator import deduplicate_and_insert
NOW=datetime(2026,9,21,12,tzinfo=timezone.utc)

@pytest.mark.parametrize('raw',[None,'not a date','2026-09-21','2099-01-01T00:00:00Z'])
def test_unknown_time_never_becomes_now(raw):
    assert _parse_published_at(raw,NOW) is None

def test_timezone_and_missing_body():
    assert _parse_published_at('2026-09-21T08:00:00-04:00',NOW)==NOW
    feed='<rss><channel><item><title>Evidence title</title><link>https://example.test/1</link></item><item><title>No link</title></item></channel></rss>'
    r=parse_feed(feed,RssSource(name='test',url='https://example.test/rss',language='en'),NOW)
    assert len(r.items)==1 and r.skipped_count==1 and r.timestamp_unknown==1
    assert r.items[0].published_at is None

@pytest.mark.asyncio
@pytest.mark.parametrize('kind,expected', [('url',1),('same',1),('cross',2),('recurring',2),('short',2)])
async def test_dedup_policies(db_session,kind,expected):
    a=ParsedNewsItem(source_name='A',source_url='https://example.test/a',title='A long recurring event headline',content='same copied body',language='en',published_at=NOW)
    b=a.model_copy(update={'source_url':'https://example.test/b'})
    if kind=='url': b=b.model_copy(update={'source_url':a.source_url})
    if kind=='cross': b=b.model_copy(update={'source_name':'B'})
    if kind=='recurring': b=b.model_copy(update={'published_at':NOW+timedelta(days=3)})
    if kind=='short':
        a=a.model_copy(update={'title':'Short','content':'body a'})
        b=b.model_copy(update={'title':'Short','content':'body b'})
    stats=await deduplicate_and_insert([a,b],db_session)
    assert stats.inserted==expected


def test_aggregator_submission_is_not_original_publication():
    source=RssSource(name='Aggregator',url='https://example.test/rss',language='en',time_quality='submission')
    feed='<rss><channel><item><title>A useful report</title><link>https://example.test/a</link><pubDate>Mon, 21 Sep 2026 12:00:00 GMT</pubDate></item></channel></rss>'
    assert parse_feed(feed,source,NOW).items[0].time_quality=='submission'
