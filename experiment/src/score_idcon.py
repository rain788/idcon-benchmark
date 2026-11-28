"""Scoring and analysis for the IdCon suites (Hard, HPRD).

Joins frozen predictions with references, replays method witnesses, and writes
scored rows, summaries, bootstrap contrasts and per-stratum tables.
Usage: python score_idcon.py <study> [--hard]
"""
import collections
import glob
import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PEN_MS = 4000.0
OUTCOMES = ['SATISFIES', 'VIOLATES', 'UNKNOWN', 'EMPTY']


def load_jsonl(pattern):
    rows = []
    for path in sorted(glob.glob(str(pattern))):
        rows += [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    return rows


PEN_WRONG_MS = 20000.0  # revision R1: PAR-10 charge for a wrong (answered) outcome


def score(study, replay=None, refs_version='r1', preds='main'):
    """refs_version: 'v1' (frozen v1 references) or 'r1' (R1 re-check overrides, if any).
    preds: 'main' = every 2 s record (v1 and R1), 'b10' = the R1 10 s records, 'v1' = v1 only."""
    out = ROOT / 'results' / study
    data = ROOT / 'data/processed' / study
    manifest = {}
    for path in sorted(data.glob('manifest*.json')):
        manifest.update({r['task_id']: r for r in json.loads(path.read_text())})
    refs = {}
    for path in sorted(glob.glob(str(ROOT / 'data/protected' / study / 'references*.jsonl'))):
        if refs_version == 'v1' and Path(path).name.startswith('references_r1'):
            continue
        refs.update({r['task_id']: r for r in load_jsonl(path)})
    files = sorted(glob.glob(str(out / 'predictions*.jsonl')))
    side = ('.b10.', '.b60.', '.r2calib.')  # extended budgets and the R2 calibration runs
    if preds in ('b10', 'b60', 'r2calib'):
        files = [f for f in files if f'.{preds}.' in Path(f).name]
    elif preds == 'v1':
        files = [f for f in files if not any(t in Path(f).name for t in side + ('.r1.', '.r2.'))]
    elif preds == 'r1':  # every 2 s record up to revision R1 (the R1 paper's tables)
        files = [f for f in files if not any(t in Path(f).name for t in side + ('.r2.',))]
    else:
        files = [f for f in files if not any(t in Path(f).name for t in side)]
    preds = []
    for f in files:
        preds += load_jsonl(f)
    seen = set()
    rows = []
    for p in preds:
        key = (p['task_id'], p['method'], p['repeat'])
        if key in seen:
            continue
        seen.add(key)
        ref = refs.get(p['task_id'])
        rec = manifest[p['task_id']]
        assessed = bool(ref and ref['complete'])
        correct = assessed and p['outcome'] == ref['label']
        certified_wrong = assessed and p['outcome'] in OUTCOMES and not correct and \
            p['method'] != 'first_match'
        rows.append(dict(task_id=p['task_id'], group_id=p['group_id'], scenario=p['scenario'],
                         family=rec['family'], entities=rec['entities'], roles=rec['roles'],
                         query_set=rec.get('query_set'),
                         par10w_ms=(1000 * p['seconds'] if correct else
                                    (PEN_WRONG_MS if p['outcome'] != 'NO_ANSWER' else PEN_MS)) if assessed else None,
                         construction=rec['construction'], variant=rec['variant'],
                         method=p['method'], repeat=p['repeat'], outcome=p['outcome'],
                         reason=p.get('reason'), seconds=p['seconds'],
                         reference=ref['label'] if ref else 'MISSING', assessed=assessed,
                         correct=correct, certified_wrong=certified_wrong,
                         answered=p['outcome'] != 'NO_ANSWER',
                         par2_ms=(1000 * p['seconds'] if correct else PEN_MS) if assessed else None,
                         n_mappings=len(p.get('mappings') or [])))
    return rows, refs, manifest


def ancestor_mean(rows, method, key='par2_ms'):
    groups = collections.defaultdict(list)
    for r in rows:
        if r['method'] == method and r['assessed']:
            groups[r['group_id']].append(r[key])
    return {g: statistics.mean(v) for g, v in groups.items()}


def summarize(rows, methods):
    out = []
    for m in methods:
        sub = [r for r in rows if r['method'] == m and r['assessed']]
        if not sub:
            continue
        anc = ancestor_mean(rows, m)
        ok = [r for r in sub if r['correct']]
        out.append(dict(method=m, assessed=len(sub), correct=len(ok),
                        answered=sum(r['answered'] for r in sub),
                        wrong=sum(r['answered'] and not r['correct'] for r in sub),
                        certified_wrong=sum(r['certified_wrong'] for r in sub),
                        success_ms=statistics.mean(1000 * r['seconds'] for r in ok) if ok else None,
                        par2_ms=statistics.mean(anc.values()),
                        ancestors=len(anc)))
    return out


def bootstrap(rows, a, b, strata, seed=1, draws=10000):
    da, db = ancestor_mean(rows, a), ancestor_mean(rows, b)
    ids = sorted(set(da) & set(db))
    delta = {g: da[g] - db[g] for g in ids}
    by = collections.defaultdict(list)
    for g in ids:
        by[strata[g]].append(g)
    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        drawn = [rng.choice(v) for k, v in sorted(by.items()) for _ in v]
        samples.append(statistics.mean(delta[g] for g in drawn))
    samples.sort()
    return dict(a=a, b=b, ancestors=len(ids), diff_ms=statistics.mean(delta.values()),
                ci95=[samples[int(.025 * draws)], samples[int(.975 * draws) - 1]],
                a_better=sum(v < 0 for v in delta.values()))


def prior_accuracy(refs, manifest, keys):
    """Leave-one-ancestor-out majority label given metadata keys."""
    complete = [(manifest[t], r['label']) for t, r in refs.items() if r['complete']]
    correct = 0
    for rec, label in complete:
        pool = collections.Counter(l for rc, l in complete
                                   if rc['group_id'] != rec['group_id'] and
                                   all(rc[k] == rec[k] for k in keys))
        if pool and pool.most_common(1)[0][0] == label:
            correct += 1
    return correct, len(complete)
