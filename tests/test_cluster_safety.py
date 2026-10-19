"""聚类失败不可破坏上一版事件，窗口标签不可碰撞。"""
import numpy as np
import pytest
from contextlib import asynccontextmanager
from sqlalchemy import select
from scripts import cluster_news as c
from src.models.event import Event

@pytest.mark.asyncio
async def test_empty_replacement_refused() -> None:
    with pytest.raises(ValueError, match='zero clusters'):
        await c.persist_clusters_to_db([], [], [])

@pytest.mark.asyncio
async def test_failed_replacement_keeps_events(db_session, sample_events, monkeypatch) -> None:
    await db_session.commit()
    ids = [e.id for e in sample_events]
    @asynccontextmanager
    async def factory():
        yield db_session
    async def fail(*args, **kwargs):
        raise RuntimeError('injected write failure')
    monkeypatch.setattr(c, 'AsyncSessionLocal', factory)
    monkeypatch.setattr(c, 'LLMClient', lambda: object())
    monkeypatch.setattr(c, '_persist_one_cluster', fail)
    with pytest.raises(RuntimeError, match='injected'):
        await c.persist_clusters_to_db([], [], [c.WindowClusterResult('2026-W01', [0], np.array([0]))])
    assert set((await db_session.scalars(select(Event.id))).all()) == set(ids)

def test_global_labels_do_not_merge_windows(monkeypatch) -> None:
    class Clusterer:
        def fit_predict(self, values):
            return np.zeros(len(values), dtype=int)
    monkeypatch.setattr(c, '_make_hdbscan_clusterer', lambda cfg: Clusterer())
    labels, stats, windows = c.cluster_by_iso_week(np.ones((8, 2)), {'a': list(range(4)), 'b':list(range(4,8))},c.ClusterConfig(4,4,False,0.3))
    assert len(set(labels)) == 2
    assert sum(s['clusters'] for s in stats) == 2
