"""Revision R2 workload IdCon-Cite: two real citation hosts with real labels.

Hosts: Cora (2,708 papers, 7 subject labels) and PubMed (19,717 papers,
3 labels), from the Planetoid repository at a fixed commit
(tools/fetch_planetoid.sh; files not redistributed, SHA-256 recorded).
Topology and vertex labels are taken unchanged; edges are made undirected and
self-loops dropped.

Queries are extracted from the host in the style of Sun & Luo (SIGMOD 2020):
a random walk from a seeded start collects k distinct vertices; the query is
the induced subgraph with the hosts' labels; it is 'dense' if its average degree
is at least 3 and 'sparse' otherwise, and connected. Sets: k in {8, 16, 24},
dense and sparse, 8 queries each per host (seeded rejection sampling, at most
200,000 walks per set; a set that cannot be filled is reported, not padded).

The observation rule is the one of IdCon-HPRD (external_hprd.py), unchanged:
unchecked roles keep their label as a unary domain; 1-4 seeded checked roles are
free; spec_true requires the query label, spec_wrong a different label drawn by
label frequency; a checked role observes S iff its entity carries it.
"""
import os
import pickle
import random
import sys
from pathlib import Path

import numpy as np

SUITE = os.environ.get('IDCON_STUDY', 'idcon_cite')
os.environ['IDCON_STUDY'] = SUITE
import hard_benchmark as hb  # noqa: E402
from external_hprd import SCENARIOS  # noqa: E402
from external_hprd_x import build_identity  # noqa: E402

ROOT = hb.ROOT
RAW = Path(os.environ.get('PLANETOID_DIR', ROOT / 'data/raw/planetoid'))
HOSTS = ['cora', 'pubmed']
SIZES = (8, 16, 24)
PER_SET = 8
MAX_WALKS = 200000
SEED = {'idcon_cite': 202611280101}.get(SUITE, int(os.environ.get('IDCON_SEED', '0')))


def _load(name):
    with open(name, 'rb') as f:
        return pickle.load(f, encoding='latin1')


def load_host(name):
    graph = _load(RAW / f'ind.{name}.graph')
    ally = _load(RAW / f'ind.{name}.ally')
    ally = np.asarray(ally.todense() if hasattr(ally, 'todense') else ally)
    ty = _load(RAW / f'ind.{name}.ty')
    ty = np.asarray(ty.todense() if hasattr(ty, 'todense') else ty)
    test = [int(x) for x in (RAW / f'ind.{name}.test.index').read_text().split()]
    n = max(max(graph), max(max(v) for v in graph.values() if v)) + 1
    labels = {}
    for i in range(ally.shape[0]):
        if ally[i].any():
            labels[i] = int(ally[i].argmax())
    for row, i in enumerate(test):
        if ty[row].any():
            labels[i] = int(ty[row].argmax())
    edges = set()
    for u, vs in graph.items():
        for v in vs:
            if u != v:
                edges.add((min(u, v), max(u, v)))
    # keep vertices that carry a label; renumber densely in original order
    keep = sorted(u for u in range(n) if u in labels)
    index = {u: i for i, u in enumerate(keep)}
    lab = {index[u]: labels[u] for u in keep}
    e = sorted((index[a], index[b]) for a, b in edges if a in index and b in index)
    return lab, e


def extract_queries(labels, edges, rng):
    n = len(labels)
    adj = [[] for _ in range(n)]
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    eset = set(edges)
    out = {}
    for k in SIZES:
        for kind in ('dense', 'sparse'):
            got, seen = [], set()
            for _ in range(MAX_WALKS):
                if len(got) == PER_SET:
                    break
                u = rng.randrange(n)
                if not adj[u]:
                    continue
                walk = [u]
                chosen = {u}
                for _step in range(50 * k):
                    u = rng.choice(adj[u])
                    if u not in chosen:
                        chosen.add(u)
                        walk.append(u)
                        if len(walk) == k:
                            break
                if len(walk) < k:
                    continue
                key = tuple(sorted(walk))
                if key in seen:
                    continue
                seen.add(key)
                pos = {v: i for i, v in enumerate(walk)}
                qedges = sorted((pos[a], pos[b]) if pos[a] < pos[b] else (pos[b], pos[a])
                                for a, b in eset if a in pos and b in pos)
                avg = 2 * len(qedges) / k
                if (kind == 'dense') != (avg >= 3):
                    continue
                got.append(([labels[v] for v in walk], qedges))
            out[f'{kind}_{k}'] = got
    return out


def generate():
    assert not (hb.DATA / 'manifest.json').exists(), 'inputs already generated'
    manifest, ancestors, src, shortfall = [], [], {}, {}
    for h, host in enumerate(HOSTS):
        for f in sorted(RAW.glob(f'ind.{host}.*')):
            src[f.name] = hb.sha(f)
        labels, edges = load_host(host)
        n = len(labels)
        freq, by_label = {}, {}
        for u, l in labels.items():
            freq[l] = freq.get(l, 0) + 1
            by_label.setdefault(l, []).append(u)
        rng = random.Random(SEED + 1000 * h)
        sets = extract_queries(labels, edges, rng)
        for qset, queries in sets.items():
            if len(queries) < PER_SET:
                shortfall[f'{host}_{qset}'] = len(queries)
            for j, (qlab_list, qedges) in enumerate(queries):
                qlab = dict(enumerate(qlab_list))
                k = len(qlab)
                index = len(ancestors)
                crng = random.Random(SEED + 7 + index)
                checked = sorted(crng.sample(range(k), crng.randint(1, 4)))
                identity = build_identity(labels, edges, qlab, qedges, checked, by_label)
                group = f'cite_{host}_{qset}_{j}'
                ipath = hb.DATA / 'identities' / f'{group}.json'
                hb.dump(ipath, identity)
                ancestors.append(dict(group_id=group, host=host, query_set=qset, roles=k,
                                      query_edges=len(identity['role_edges']), checked_roles=checked,
                                      query_labels=qlab_list))
                for scenario in SCENARIOS:
                    tables, required = {}, {}
                    for r in checked:
                        want = qlab[r]
                        if scenario == 'spec_wrong':
                            pool = sorted(l for l in freq if l != qlab[r])
                            want = crng.choices(pool, weights=[freq[l] for l in pool])[0]
                        required[r] = want
                        tables[str(r)] = [0 if labels[u] == want else 2 for u in range(n)]
                    task = f'{group}__{scenario}'
                    tpath = hb.DATA / 'tables' / f'{task}.json'
                    hb.dump(tpath, {'role_states': tables, 'global_state': 0})
                    manifest.append(dict(task_id=task, group_id=group, family=f'cite_{host}',
                                         query_set=qset, entities=n, roles=k,
                                         construction='extracted', variant='label_domains',
                                         scenario=scenario,
                                         params=dict(checked=checked, required_labels=required),
                                         identity_file=ipath.relative_to(ROOT).as_posix(),
                                         tables_file=tpath.relative_to(ROOT).as_posix()))
    hb.dump(hb.DATA / 'ancestors.json', ancestors)
    hb.dump(hb.DATA / 'manifest.json', manifest)
    hb.dump(hb.PRIVATE / 'construction_maps.json', {})
    hb.dump(hb.DATA / 'source_hashes.json', src)
    hb.dump(hb.DATA / 'generation_report.json', dict(shortfall=shortfall))
    hb.dump(hb.DATA / 'input_hashes.json', {r['task_id']: {k: hb.sha(ROOT / r[k]) for k in ('identity_file', 'tables_file')} for r in manifest})
    print('GENERATED', SUITE, len(ancestors), len(manifest), 'shortfall', shortfall)


if __name__ == '__main__':
    generate()
