"""Revision R1 third-party workloads on the HPRD graph.

IdCon-HPRD-X   HPRD data graph with query graphs of 8, 16, 24 and 32 vertices,
               dense and sparse, from the public artifact of CEMR (Yang et al.,
               PVLDB 19(7), 2026; github.com/pkumod/CEMR, commit 1eb4b07,
               test/test_data). 12 queries per set are drawn with a fixed seed.
               The query files are not redistributed: tools/fetch_cemr_queries.sh
               retrieves them and the manifest records their SHA-256.
IdCon-HPRD-H   held-out split: Sun & Luo dense-16 queries 101-200 (the release
               used queries 1-100). Inputs are public; reference labels are
               kept out of the public repository and only their SHA-256 is
               published (commitment), so the split can serve as a hidden test.

The observation rule is unchanged from IdCon-HPRD (external_hprd.py): unchecked
roles keep their query label as a unary domain; 1-4 seeded checked roles are
free and observe S iff the entity carries the required label; spec_true uses the
query's own label, spec_wrong a different label drawn by label frequency.
"""
import hashlib, os, random, sys
from pathlib import Path
SUITE = os.environ.get('IDCON_STUDY', 'idcon_hprd_x')
os.environ['IDCON_STUDY'] = SUITE
import hard_benchmark as hb
from external_hprd import parse, SCENARIOS

ROOT = hb.ROOT
CEMR = Path(os.environ.get('CEMR_DIR', ROOT / 'data/raw/cemr_hprd'))
SUNLUO = Path(os.environ.get('HPRD_DIR', ROOT / 'data/raw/hprd_sun_luo'))
SETS = [f'{d}_{k}' for k in (8, 16, 24, 32) for d in ('dense', 'sparse')]
PER_SET = 12
SEED = {'idcon_hprd_x': 202611270101, 'idcon_hprd_h': 202611270201}.get(SUITE, 0)


def build_identity(labels, edges, qlab, qedges, checked, by_label):
    n = len(labels); k = len(qlab)
    return dict(candidate_xyz=[[float(u), 0., 0.] for u in range(n)],
                candidate_edges=[list(e) for e in sorted(set(tuple(sorted(e)) for e in edges))],
                role_count=k,
                role_edges=[[r, s, None, False] for r, s in sorted(set(tuple(sorted(e)) for e in qedges))],
                registered_positions={}, coordinate_tolerance=1e-9, length_tolerance=1e-3,
                domain_complete=True, injective=True,
                role_domains={str(r): sorted(by_label.get(qlab[r], [])) for r in range(k) if r not in checked})


def generate():
    assert not (hb.DATA / 'manifest.json').exists(), 'inputs already generated'
    labels, edges = parse(SUNLUO / 'HPRD.graph')
    n = len(labels)
    freq, by_label = {}, {}
    for u, l in labels.items():
        freq[l] = freq.get(l, 0) + 1
        by_label.setdefault(l, []).append(u)
    if SUITE == 'idcon_hprd_x':
        pick = random.Random(SEED)
        queries = [(s, CEMR / 'query_graph' / f'query_{s}_{i}.graph')
                   for s in SETS for i in sorted(pick.sample(range(1, 201), PER_SET))]
    else:
        queries = [('dense_16', SUNLUO / 'query_graph' / f'query_dense_16_{i}.graph') for i in range(101, 201)]
    manifest, ancestors, src = [], [], {'HPRD.graph': hb.sha(SUNLUO / 'HPRD.graph')}
    for index, (qset, path) in enumerate(queries):
        src[path.name if SUITE == 'idcon_hprd_h' else f'cemr/{path.name}'] = hb.sha(path)
        qlab, qedges = parse(path)
        k = len(qlab)
        rng = random.Random(SEED + index)
        checked = sorted(rng.sample(range(k), rng.randint(1, 4)))
        identity = build_identity(labels, edges, qlab, qedges, checked, by_label)
        prefix = 'hprdx' if SUITE == 'idcon_hprd_x' else 'hprdh'
        group = f'{prefix}_{path.stem}'
        ipath = hb.DATA / 'identities' / f'{group}.json'
        hb.dump(ipath, identity)
        ancestors.append(dict(group_id=group, query=path.name, query_set=qset, roles=k,
                              query_edges=len(identity['role_edges']), checked_roles=checked,
                              query_labels=[qlab[r] for r in range(k)]))
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
            manifest.append(dict(task_id=task, group_id=group, family='hprd', query_set=qset,
                                 entities=n, roles=k, construction='third_party',
                                 variant='label_domains', scenario=scenario,
                                 params=dict(checked=checked, required_labels=required),
                                 identity_file=ipath.relative_to(ROOT).as_posix(),
                                 tables_file=tpath.relative_to(ROOT).as_posix()))
    hb.dump(hb.DATA / 'ancestors.json', ancestors)
    hb.dump(hb.DATA / 'manifest.json', manifest)
    hb.dump(hb.PRIVATE / 'construction_maps.json', {})
    hb.dump(hb.DATA / 'source_hashes.json', src)
    hb.dump(hb.DATA / 'input_hashes.json', {r['task_id']: {k: hb.sha(ROOT / r[k]) for k in ('identity_file', 'tables_file')} for r in manifest})
    print('GENERATED', SUITE, len(ancestors), len(manifest))


if __name__ == '__main__':
    generate()
