"""Pilot validation of the revision baselines (not part of any released suite).

Small instances are drawn with the IdCon-Hard generator under a separate pilot
seed (n=48 entities, k=6 roles, all six families, both constructions and
variants, all scenarios) plus HPRD with 4-vertex queries from the CEMR artifact.
Every method is compared with an exhaustive reference: NetworkX VF2 run to
completion with a 30 s budget, cross-checked against LAD2025 two-query
consensus with a 60 s budget. The pilot only checks agreement; its timings are
not reported as results.
"""
import itertools, json, os, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault('IDCON_STUDY', 'revision_pilot')
import hard_benchmark as hb
from revision_baselines import enum_glasgow, enum_nx, asp_cautious
from lad_baseline import diagnose_tables as lad
from glasgow_baseline import diagnose_tables as glasgow

PILOT_SEED = 777001
CEMR = Path(os.environ.get('CEMR_DIR', '/tmp/pkumod_CEMR/test/test_data'))


def legal(identity, mapping):
    from coordination_confirmation_data import legal as _legal
    return _legal(identity, mapping)


def outcome(ans):
    return hb.outcome(ans)


def pilot_tasks():
    tasks = []
    cells = list(itertools.product(hb.FAMILIES, hb.CONSTRUCTIONS, hb.VARIANTS))
    for i, (family, construction, variant) in enumerate(cells):
        identity, checked, selected, g, q, detail = hb.make_ancestor(family, 48, 6, construction, variant, PILOT_SEED + i)
        rng = random.Random(PILOT_SEED + 500 + i)
        for scenario in hb.SCENARIOS:
            tables, _ = hb.make_tables(scenario, 48, checked, selected, g, q, rng)
            ident = identity
            if scenario == 'perturbed':
                ident, _ = hb.perturb(identity, q, rng, detail['anchor_roles'])
            tasks.append((f'pilot_{family}_{construction}_{variant}__{scenario}', ident, tables))
    # HPRD with 4-vertex queries (domain-restricted roles)
    import external_hprd as eh
    labels, edges = eh.parse(CEMR / 'data_graph' / 'hprd.graph')
    n = len(labels)
    for j in range(1, 11):
        qlab, qedges = eh.parse(CEMR / 'query_graph' / f'query_dense_4_{j}.graph')
        k = len(qlab); rng = random.Random(PILOT_SEED + 900 + j)
        checked = sorted(rng.sample(range(k), rng.randint(1, 2)))
        by_label = {}
        for u, l in labels.items():
            by_label.setdefault(l, []).append(u)
        identity = dict(candidate_xyz=[[float(u), 0., 0.] for u in range(n)],
                        candidate_edges=[list(e) for e in sorted(set(tuple(sorted(e)) for e in edges))],
                        role_count=k, role_edges=[[r, s, None, False] for r, s in sorted(set(tuple(sorted(e)) for e in qedges))],
                        registered_positions={}, coordinate_tolerance=1e-9, length_tolerance=1e-3,
                        domain_complete=True, injective=True,
                        role_domains={str(r): sorted(by_label.get(qlab[r], [])) for r in range(k) if r not in checked})
        tables = {r: [0 if labels[u] == qlab[r] else 2 for u in range(n)] for r in checked}
        tasks.append((f'pilot_hprd_dense4_{j}', identity, tables))
    return tasks


def main():
    out = Path(sys.argv[1]); out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, identity, tables in pilot_tasks():
        truth = enum_nx(identity, tables, 0, 30.)
        ref = lad(identity, tables, 0, 60.)
        row = dict(task=name, truth=outcome(truth), lad60=outcome(ref), truth_solutions=truth.get('solutions'))
        for m, f in [('enum_glasgow', enum_glasgow), ('enum_nx', enum_nx), ('asp_cautious', asp_cautious),
                     ('lad_state', lad), ('glasgow', glasgow)]:
            a = f(identity, tables, 0, 5.)
            row[m] = outcome(a); row[m + '_s'] = round(a['seconds'], 3)
            row[m + '_replay'] = all(legal(identity, mp) for mp in a.get('mappings') or [])
        rows.append(row)
        print(json.dumps(row), flush=True)
    out.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    bad = [r for r in rows for m in ('enum_glasgow', 'enum_nx', 'asp_cautious', 'lad_state', 'glasgow')
           if r[m] != 'NO_ANSWER' and r['truth'] != 'NO_ANSWER' and r[m] != r['truth']]
    unrep = [r for r in rows for m in ('enum_glasgow', 'enum_nx', 'asp_cautious') if not r[m + '_replay']]
    print('TASKS', len(rows), 'DISAGREEMENTS', len(bad), 'REPLAY_FAILURES', len(unrep),
          'TRUTH_UNRESOLVED', sum(r['truth'] == 'NO_ANSWER' for r in rows),
          'LAD_VS_TRUTH_MISMATCH', sum(r['truth'] != r['lad60'] for r in rows if 'NO_ANSWER' not in (r['truth'], r['lad60'])))


if __name__ == '__main__':
    main()
