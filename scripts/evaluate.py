"""Evaluate a manually labeled local query set against an indexed database.

Labels: [{"query":"...", "expected_ids":[1,2], "kind":"text|visual"}]
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from recall.engine import Ollama
from recall.store import Store

parser=argparse.ArgumentParser()
parser.add_argument('--data',default='data')
parser.add_argument('--labels',required=True)
parser.add_argument('--keyword-only',action='store_true')
args=parser.parse_args()
store=Store(Path(args.data));ollama=Ollama()
labels=json.loads(Path(args.labels).read_text(encoding='utf-8-sig'))
if not args.keyword_only and not ollama.readiness()['embedding']:
    raise SystemExit('Embedding model unavailable. Install it or explicitly use --keyword-only.')
results=[]
for case in labels:
    q=case['query']
    # Warm up/cache query embedding before timing warm retrieval.
    vector=None if args.keyword_only else ollama.embed([q],query=True)[0]
    started=time.perf_counter()
    matches,_=store.search(q,vector,limit=5)
    ms=(time.perf_counter()-started)*1000
    ids=[r['id'] for r in matches]
    results.append({**case,'top5':ids,'hit':bool(set(ids)&set(case['expected_ids'])),'warm_retrieval_ms':round(ms,2)})
summary={'mode':'keyword' if args.keyword_only else 'hybrid','queries':len(results),'hits_at_5':sum(r['hit'] for r in results),'median_warm_retrieval_ms':round(statistics.median(r['warm_retrieval_ms'] for r in results),2),'results':results}
(store.root/'evaluation.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='results'},indent=2))
