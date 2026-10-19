"""冻结语料的候选/审核后召回对比；不写业务库或向量库。"""

import argparse
import asyncio
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sys
import numpy as np
from sklearn.cluster import HDBSCAN

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api'))
from src.models.news import News
from src.llm import LLMClient
from src.services.event_quality import build_candidates
from src.services.story_matching import fragment_candidates
from src.services.story_review import review_story, membership_hash, StoryReview, MATCH_VERSION


def pair_counts(rows: list[dict], groups: list[list[News]]) -> dict:
    assignment = {n.id: i for i, group in enumerate(groups) for n in group}
    counts: Counter = Counter()
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            expected = a['event_label'] == b['event_label']
            same = assignment[a['id']] == assignment[b['id']]
            key = 'true_pairs' if same and expected else 'false_merges' if same else 'missed_pairs' if expected else 'separated_negatives'
            counts[key] += 1
    return dict(counts)


async def main(args: argparse.Namespace) -> None:
    corpus = json.loads(Path(args.corpus).read_text())
    pool_path = Path('/tmp/phase3-evaluation-pool.json')
    if pool_path.exists():
        pool = json.loads(pool_path.read_text())
    else:
        from src.embedding import EmbeddingClient, EmbeddingRequest
        embedder = EmbeddingClient()
        encoded = {}
        for start in range(0, len(corpus['articles']), 32):
            batch = corpus['articles'][start:start+32]
            result = await embedder.embed(EmbeddingRequest(texts=[r['title'] + '\n\n' + r['content'][:2000] for r in batch]))
            encoded.update({str(r['id']): v.vector for r,v in zip(batch,result.results,strict=True)})
        pool = {'articles': corpus['articles'], 'vectors': encoded}
    metadata_path = Path('evaluation/phase3/source-metadata.json')
    frozen_metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    metadata = {r['id']: frozen_metadata.get(str(r['id']), r.get('metadata', {})) for r in pool['articles']}
    rows = corpus['articles']
    news = [News(id=r['id'], title=r['title'], content=r['content'], source_name=r['publisher'],
                 source_url=r['url'], language=r['language'], time_quality='verified',
                 published_at=datetime.fromisoformat(r['published_at']), raw_metadata=metadata.get(r['id'], {})) for r in rows]
    vectors = {n.id: pool['vectors'][str(n.id)] for n in news}
    initial = build_candidates(news, [vectors[n.id] for n in news])
    cache_path = Path('/tmp/phase3-identity-cache.json')
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    llm = LLMClient()
    calls = 0

    async def assess(group: list[News]) -> StoryReview | None:
        nonlocal calls
        key = membership_hash(group)
        if key not in cache:
            if calls >= args.budget:
                return None
            calls += 1
            try:
                cache[key] = (await review_story(llm, group)).model_dump()
            except Exception as exc:
                cache[key] = {'relation': 'ambiguous', 'identity': '', 'reason': type(exc).__name__, 'anchors': []}
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
            print('review', calls, len(group), cache[key]['relation'], flush=True)
        return StoryReview.model_validate(cache[key])

    try:
        groups = []
        for group in initial:
            decision = await assess(group) if len(group) > 1 else None
            groups.extend([group] if len(group) == 1 or (decision and decision.accepted) else [[n] for n in group])
        merges = []
        while True:
            changed = False
            for i, j, score in fragment_candidates(groups, vectors):
                union = groups[i] + groups[j]
                decision = await assess(union)
                if decision and decision.accepted:
                    merges.append({'ids': [n.id for n in union], 'similarity': score, 'review': decision.model_dump()})
                    groups[i] = union
                    groups.pop(j)
                    changed = True
                    break
            if not changed:
                break
        result = {'matching_version': MATCH_VERSION, 'articles': len(news), 'initial_groups': [[n.id for n in g] for g in initial],
                  'reviewed_groups': [[n.id for n in g] for g in groups], 'merges': merges,
                  'new_identity_calls': calls, 'usage': llm.metrics,
                  'scope': 'Identity-reviewed grouping; summary entailment is a separate mandatory publication gate.'}
        if all('event_label' in r for r in rows):
            result['before'] = pair_counts(rows, initial)
            result['after'] = pair_counts(rows, groups)
            matrix = np.asarray([vectors[n.id] for n in news]); matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
            labels = HDBSCAN(min_cluster_size=2, min_samples=2, metric='euclidean', copy=True).fit_predict(matrix)
            assignments = {n.id: k for k, g in enumerate(initial) for n in g}
            diagnosis = []
            for i,a in enumerate(rows):
                for j in range(i+1,len(rows)):
                    b=rows[j]; positive=a['event_label']==b['event_label']; together=assignments[a['id']]==assignments[b['id']]
                    if positive == together:
                        continue
                    score=float(matrix[i]@matrix[j]);threshold=.72 if labels[i]>=0 and labels[i]==labels[j] else .82
                    diagnosis.append({'ids':[a['id'],b['id']], 'expected_same':positive,
                        'similarity':score,'threshold':threshold,'cause': 'action_boundary' if not positive else
                        'pair_threshold' if score<threshold else 'complete_link_or_greedy_group_constraint'})
            result['diagnostics']=diagnosis
        else:
            before={n.id:i for i,g in enumerate(initial) for n in g};after={n.id:i for i,g in enumerate(groups) for n in g}
            result['relationship_cases']=[{**c,'before_joined':before[c['ids'][0]]==before[c['ids'][1]],
                'after_joined':after[c['ids'][0]]==after[c['ids'][1]]} for c in corpus['relationship_cases']]
        Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k in {'articles','before','after','new_identity_calls','usage'}}))
    finally:
        await llm.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--corpus',default='evaluation/global-events.json')
    parser.add_argument('--output',default='/tmp/phase3-recall-baseline.json')
    parser.add_argument('--budget',type=int,default=180)
    asyncio.run(main(parser.parse_args()))
