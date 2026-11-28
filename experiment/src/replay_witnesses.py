"""Replay every positive witness returned by any method against the original
constraints (anchors, injectivity, unary domains, edges, metric tolerances).
python replay_witnesses.py <study> [<study> ...]
"""
import collections
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coordination_confirmation_data import legal
import score_idcon as sc

ROOT = sc.ROOT
result = {}
for study in sys.argv[1:]:
    data = ROOT / 'data/processed' / study
    manifest = {}
    for path in sorted(data.glob('manifest*.json')):
        manifest.update({r['task_id']: r for r in json.loads(path.read_text())})
    cache = {}
    counts = collections.Counter()
    failures = []
    preds = sc.load_jsonl(ROOT / 'results' / study / 'predictions*.jsonl')
    preds.sort(key=lambda p: manifest[p['task_id']]['identity_file'])
    for p in preds:
        maps = p.get('mappings') or []
        if not maps:
            continue
        f = manifest[p['task_id']]['identity_file']
        if f not in cache:
            cache.clear()
            cache[f] = json.loads((ROOT / f).read_text())
        for m in maps:
            ok = legal(cache[f], m)
            counts[p['method'], ok] += 1
            if not ok:
                failures.append((p['task_id'], p['method'], p['repeat']))
    result[study] = dict(witnesses=sum(counts.values()), failures=len(failures),
                         by_method={f'{m}|{ok}': c for (m, ok), c in counts.items()},
                         failure_examples=failures[:10])
    print(study, result[study]['witnesses'], 'witnesses,', len(failures), 'failures', flush=True)
# v1.1 wrote results/witness_replay.json (frozen); revision R2 writes
# results/revision_r2/witness_replay_r2.json (IDCON_REPLAY_OUT)
(ROOT / os.environ.get('IDCON_REPLAY_OUT', 'results/witness_replay.json')).write_text(json.dumps(result, indent=1))
