"""Third-party workload: HPRD data graph and dense-16 queries from Sun & Luo
(SIGMOD 2020, RapidsAtHKUST/SubgraphMatching test set).

Graph topology, vertex labels, query structure and query labels are all taken
unchanged from the third-party files. The benchmark adds only (i) the seeded
choice of which query roles are checked and (ii) the rule that a checked role
observes S when the entity carries the required label and V otherwise.
Unchecked roles keep their label as a unary identity constraint.
"""
import json, os, random, sys, hashlib
from pathlib import Path
os.environ.setdefault('IDCON_STUDY', 'idcon_hprd')
import hard_benchmark as hb

SRC = Path(os.environ.get('HPRD_DIR', Path(__file__).resolve().parents[1] / 'data' / 'raw' / 'hprd_sun_luo'))
SEED = 202611261130
QUERIES = 100
SCENARIOS = ['spec_true', 'spec_wrong']


def parse(path):
    labels, edges = {}, []
    for line in Path(path).read_text().splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == 'v':
            labels[int(p[1])] = int(p[2])
        elif p[0] == 'e':
            edges.append((int(p[1]), int(p[2])))
    return labels, edges


def generate():
    labels, edges = parse(SRC / 'HPRD.graph')
    n = len(labels)
    freq = {}
    for l in labels.values():
        freq[l] = freq.get(l, 0) + 1
    by_label = {}
    for u, l in labels.items():
        by_label.setdefault(l, []).append(u)
    names = [f'query_dense_16_{i}.graph' for i in range(1, QUERIES + 1)]
    manifest, ancestors = [], []
    for index, name in enumerate(names):
        qlab, qedges = parse(SRC / 'query_graph' / name)
        k = len(qlab)
        rng = random.Random(SEED + index)
        checked = sorted(rng.sample(range(k), rng.randint(1, 4)))
        domains = {str(r): sorted(by_label.get(qlab[r], [])) for r in range(k) if r not in checked}
        identity = dict(candidate_xyz=[[float(u), 0., 0.] for u in range(n)],
                        candidate_edges=[list(e) for e in sorted(set(tuple(sorted(e)) for e in edges))],
                        role_count=k, role_edges=[[r, s, None, False] for r, s in sorted(set(tuple(sorted(e)) for e in qedges))],
                        registered_positions={}, coordinate_tolerance=1e-9, length_tolerance=1e-3,
                        domain_complete=True, injective=True, role_domains=domains)
        group = 'hprd_' + name.replace('.graph', '')
        ipath = hb.DATA / 'identities' / f'{group}.json'
        hb.dump(ipath, identity)
        ancestors.append(dict(group_id=group, query=name, roles=k, query_edges=len(identity['role_edges']),
                              checked_roles=checked, query_labels=[qlab[r] for r in range(k)]))
        for scenario in SCENARIOS:
            tables, required = {}, {}
            for r in checked:
                want = qlab[r]
                if scenario == 'spec_wrong':
                    pool = sorted(l for l in freq if l != qlab[r])
                    want = rng.choices(pool, weights=[freq[l] for l in pool])[0]
                required[r] = want
                tables[str(r)] = [0 if labels[u] == want else 2 for u in range(n)]
            task = f'{group}__{scenario}'
            tpath = hb.DATA / 'tables' / f'{task}.json'
            hb.dump(tpath, {'role_states': tables, 'global_state': 0})
            manifest.append(dict(task_id=task, group_id=group, family='hprd', entities=n, roles=k,
                                 construction='third_party', variant='label_domains', scenario=scenario,
                                 params=dict(checked=checked, required_labels=required),
                                 identity_file=ipath.relative_to(hb.ROOT).as_posix(),
                                 tables_file=tpath.relative_to(hb.ROOT).as_posix()))
    hb.dump(hb.DATA / 'ancestors.json', ancestors)
    hb.dump(hb.DATA / 'manifest.json', manifest)
    hb.dump(hb.PRIVATE / 'construction_maps.json', {})
    src = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [SRC / 'HPRD.graph'] + [SRC / 'query_graph' / x for x in names]}
    hb.dump(hb.DATA / 'source_hashes.json', src)
    print('GENERATED', len(ancestors), len(manifest))


if __name__ == '__main__':
    generate()
