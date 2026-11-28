"""IdCon-Hard: harder identity-consensus benchmark population.

Design goals (see reports/hard_confirmation_protocol.md):
  * instances span easy to budget-limited sizes;
  * labels depend on graph structure, not on the scenario name alone;
  * metric edges and empty identity spaces are exercised;
  * every method runs as one end-to-end call under the same budget.
The generator never calls a solver; labels are produced only after predictions.
"""
import argparse
import collections
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import sys
import time

import networkx as nx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
NAME = os.environ.get('IDCON_STUDY', 'idcon_hard')
OUT = ROOT / 'results' / NAME
DATA = ROOT / 'data/processed' / NAME
PRIVATE = ROOT / 'data/protected' / NAME
SEED = int(os.environ.get('IDCON_SEED', '202611260901'))
BUDGET = float(os.environ.get('IDCON_BUDGET', '2.0'))
REPEATS = int(os.environ.get('IDCON_REPEATS', '2'))
FAMILIES = ['geometric', 'preferential', 'small_world', 'regular', 'erdos',
            'articulation_modules']
TIERS = [(2048, 48), (4096, 64), (8192, 96)]
# Revision R2 (IdCon-Hard-X, IdCon-Hard-H): tiers, host density, variants and
# scenarios can be overridden; the defaults reproduce v1/R1 exactly.
if os.environ.get('IDCON_TIERS'):
    TIERS = [tuple(int(x) for x in t.split(':')) for t in os.environ['IDCON_TIERS'].split(',')]
DENSITY = int(os.environ.get('IDCON_DENSITY', '1'))
COMBOS = None  # (construction, variant) pairs kept; None keeps every pair
if os.environ.get('IDCON_COMBOS'):
    COMBOS = [tuple(c.split(':')) for c in os.environ['IDCON_COMBOS'].split(',')]
CONSTRUCTIONS = ['forest', 'induced']
VARIANTS = ['plain', 'constrained']
SCENARIOS = ['decoy_v', 'decoy_u', 'decoy_s', 'mixed', 'background', 'perturbed']
if os.environ.get('IDCON_SCENARIOS'):
    SCENARIOS = os.environ['IDCON_SCENARIOS'].split(',')
# v1 registered methods (v1.0 also ran two solvers that Amendment 4 removed) and the
# revision R1 tool baselines; glasgow_staged is selected explicitly.
METHODS = ['lad_state', 'glasgow', 'whole_cp', 'traditional_cp', 'first_match',
           'enum_glasgow', 'enum_nx', 'asp_cautious']
CHECKED = 8
GRID = 4
LENGTH_TOL = 1e-3


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf8')


# ---------------------------------------------------------------- generation
def make_ancestor(family, n, k, construction, variant, seed):
    from submission_data import graph, bfs_nodes
    rng = random.Random(seed)
    g = graph(family, n, seed, DENSITY)
    selected = bfs_nodes(g, rng.randrange(n), k, rng)
    q = g.subgraph(selected).copy()
    if construction == 'forest':
        forest = nx.Graph()
        forest.add_nodes_from(selected)
        for component in nx.connected_components(q):
            forest.add_edges_from(nx.bfs_edges(q, min(component)))
        q = forest
    roles = {u: r for r, u in enumerate(selected)}
    q = nx.relabel_nodes(q, roles)
    # Integer spacing classes make many host edges share one length, so a
    # metric edge prunes candidates without pinning the identity.
    nrng = np.random.default_rng(seed)
    xyz = nrng.integers(0, GRID + 1, size=(n, 3)).astype(float)
    xyz[:, 0] += (np.arange(n) + 1) * 1e-8
    anchors, metric = [], set()
    if variant == 'constrained':
        anchors = sorted(q, key=lambda r: (-q.degree[r], r))[:2]
        edges = sorted(q.edges())
        metric = set(map(tuple, rng.sample(edges, max(1, round(.3 * len(edges))))))
    role_edges = []
    for r, s in sorted(q.edges()):
        length = None
        if (r, s) in metric:
            length = float(np.linalg.norm(xyz[selected[r]] - xyz[selected[s]]))
        role_edges.append([r, s, length, False])
    free = sorted(set(q) - set(anchors))
    checked = rng.sample(free, min(CHECKED, len(free)))
    identity = dict(
        candidate_xyz=xyz.tolist(),
        candidate_edges=[list(e) for e in sorted(g.edges())],
        role_count=k, role_edges=role_edges,
        registered_positions={str(r): xyz[selected[r]].tolist() for r in anchors},
        coordinate_tolerance=1e-9, length_tolerance=LENGTH_TOL,
        domain_complete=True, injective=True)
    detail = dict(anchor_roles=anchors, metric_edges=len(metric),
                  query_edges=q.number_of_edges(), host_edges=g.number_of_edges(),
                  query_components=nx.number_connected_components(q.subgraph(free)))
    return identity, checked, selected, g, q, detail


def decoys(g, q, selected, role, radius):
    centre = selected[role]
    ball = nx.single_source_shortest_path_length(g, centre, cutoff=radius)
    used = set(selected)
    need = q.degree[role]
    return sorted(u for u in ball if u not in used and g.degree[u] >= need)


def make_tables(scenario, n, checked, selected, g, q, rng):
    radius = rng.choice([1, 2])
    rate = rng.uniform(.05, .6)
    count = rng.randint(1, len(checked))
    roles = rng.sample(checked, count)
    params = dict(radius=radius, decoy_rate=round(rate, 4), decoy_roles=count)
    base_value = 2 if scenario == 'decoy_s' else 0
    tables = {r: [base_value] * n for r in checked}
    if scenario in ('decoy_v', 'decoy_u', 'decoy_s', 'mixed', 'perturbed'):
        mark = {'decoy_v': 2, 'decoy_u': 1, 'decoy_s': 0, 'perturbed': 2}.get(scenario)
        for r in roles:
            for u in decoys(g, q, selected, r, radius):
                if rng.random() < rate:
                    tables[r][u] = mark if mark is not None else rng.choice([1, 2])
    if scenario in ('mixed', 'background'):
        lo, hi = (1e-4, 1e-2) if scenario == 'mixed' else (1e-4, 3e-2)
        p = math.exp(rng.uniform(math.log(lo), math.log(hi)))
        params['background_rate'] = round(p, 6)
        protected = set(selected)
        for r in checked:
            for u in range(n):
                if u not in protected and rng.random() < p:
                    tables[r][u] = 2
    return tables, params


def make_focal_tables(n, checked, selected, g, q, rng):
    """focal_v as in Amendment 1 (generate_focal), drawn from the scenario stream."""
    focal = rng.choice(checked)
    radius = rng.choice([1, 2])
    rate = rng.uniform(.05, .6)
    tables = {r: [0] * n for r in checked}
    tables[focal] = [2] * n
    for u in decoys(g, q, selected, focal, radius):
        if rng.random() < rate:
            tables[focal][u] = 0
    return tables, dict(focal_role=focal, radius=radius, decoy_rate=round(rate, 4))


def perturb(identity, q, rng, anchors):
    """Add 1-3 required edges between non-adjacent roles at query distance 2."""
    free = set(q) - set(anchors)
    candidates = sorted({tuple(sorted((r, s))) for r in free for t in q[r]
                         for s in q[t] if s != r and s in free and not q.has_edge(r, s)})
    if not candidates:
        candidates = sorted(tuple(sorted(p)) for p in itertools.combinations(sorted(free), 2)
                            if not q.has_edge(*p))
    added = rng.sample(candidates, min(len(candidates), rng.randint(1, 3)))
    new = dict(identity)
    new['role_edges'] = sorted(identity['role_edges'] + [[r, s, None, False] for r, s in added])
    return new, added


def generate(limit=None):
    assert not (DATA / 'manifest.json').exists(), 'inputs already generated'
    cells = list(itertools.product(FAMILIES, TIERS, CONSTRUCTIONS, VARIANTS))
    if COMBOS:
        cells = [c for c in cells if (c[2], c[3]) in COMBOS]
    if limit:
        cells = cells[:limit]
    manifest, ancestors, maps = [], [], {}
    for index, (family, (n, k), construction, variant) in enumerate(cells):
        t0 = time.perf_counter()
        group = f'h_{family}_n{n}_q{k}_{construction}_{variant}' + (f'_d{DENSITY}' if DENSITY != 1 else '')
        identity, checked, selected, g, q, detail = make_ancestor(
            family, n, k, construction, variant, SEED + 1000 + index)
        ipath = DATA / 'identities' / f'{group}.json'
        dump(ipath, identity)
        maps[group] = selected
        ancestors.append(dict(group_id=group, family=family, entities=n, roles=k,
                              construction=construction, variant=variant,
                              checked_roles=checked, **detail))
        rng = random.Random(SEED + 100000 + index)
        for scenario in SCENARIOS:
            task = f'{group}__{scenario}'
            if scenario == 'focal_v':
                tables, params = make_focal_tables(n, checked, selected, g, q, rng)
            else:
                tables, params = make_tables(scenario, n, checked, selected, g, q, rng)
            path_identity = ipath
            if scenario == 'perturbed':
                pert, added = perturb(identity, q, rng, detail['anchor_roles'])
                path_identity = DATA / 'identities' / f'{task}.json'
                dump(path_identity, pert)
                params['added_edges'] = added
            tpath = DATA / 'tables' / f'{task}.json'
            dump(tpath, {'role_states': {str(r): v for r, v in tables.items()},
                         'global_state': 0})
            manifest.append(dict(task_id=task, group_id=group, family=family,
                                 entities=n, roles=k, construction=construction,
                                 variant=variant, scenario=scenario, params=params,
                                 identity_file=path_identity.relative_to(ROOT).as_posix(),
                                 tables_file=tpath.relative_to(ROOT).as_posix()))
        print('GEN', index, group, round(time.perf_counter() - t0, 1), flush=True)
    dump(DATA / 'ancestors.json', ancestors)
    dump(DATA / 'manifest.json', manifest)
    dump(PRIVATE / 'construction_maps.json', maps)
    hashes = {r['task_id']: {k: sha(ROOT / r[k]) for k in ('identity_file', 'tables_file')}
              for r in manifest}
    dump(DATA / 'input_hashes.json', hashes)
    print('GENERATED', len(ancestors), len(manifest), flush=True)


# ---------------------------------------------------------------- methods
def first_match(identity, tables, base, budget):
    """Existential shortcut: report the state of the first identity found."""
    from lad_baseline import ask
    from projection_engine import Deadline
    start = time.perf_counter()
    try:
        found = ask(identity, tables, base, {}, start + budget)
        if found is None:
            answer = dict(label='UNKNOWN', reason='identity_inconsistent', certificate=True,
                          mappings=[])
        else:
            answer = dict(label=['SATISFIES', 'UNKNOWN', 'VIOLATES'][found['state']],
                          reason='first_identity_state', certificate=False,
                          mappings=[found['mapping']])
    except Deadline:
        answer = dict(label='UNKNOWN', reason='budget', certificate=False, mappings=[])
    answer['seconds'] = time.perf_counter() - start
    return answer


def dispatch(method, identity, tables, base, budget):
    if method == 'lad_state':
        from lad_baseline import diagnose_tables
        return diagnose_tables(identity, tables, base, budget)
    if method == 'glasgow':
        from glasgow_baseline import diagnose_tables
        return diagnose_tables(identity, tables, base, budget)
    if method == 'glasgow_staged':
        from glasgow_baseline import diagnose_tables
        return diagnose_tables(identity, tables, base, budget, extra=('--staged',))
    if method == 'first_match':
        return first_match(identity, tables, base, budget)
    if method == 'sat_cadical':  # revision R2
        from sat_baseline import diagnose_tables
        return diagnose_tables(identity, tables, base, budget)
    if method in ('enum_glasgow', 'enum_nx', 'asp_cautious'):  # revision R1
        from revision_baselines import METHODS as R1_METHODS
        return R1_METHODS[method](identity, tables, base, budget)
    from comparison_baselines import solve
    return solve(method, identity, tables, base, budget)


def outcome(answer):
    """Map a method answer to the five-way benchmark outcome."""
    if not answer.get('certificate') and answer.get('reason') != 'first_identity_state':
        return 'NO_ANSWER'
    if answer.get('reason') == 'identity_inconsistent':
        return 'EMPTY'
    return answer['label']


def run_shard(worker, workers, methods=None):
    methods = methods or METHODS
    mname = os.environ.get('IDCON_MANIFEST', 'manifest.json')
    manifest = read(DATA / mname)
    out = OUT / (f'predictions.w{worker}.jsonl' if mname == 'manifest.json' else f'predictions.{mname[:-5]}.w{worker}.jsonl')
    if os.environ.get('IDCON_PRED_TAG'):
        out = OUT / f"predictions.{os.environ['IDCON_PRED_TAG']}.{out.name[len('predictions.'):]}"
    done = set()
    if out.exists():
        for line in out.read_text(encoding='utf8').splitlines():
            row = json.loads(line)
            done.add((row['task_id'], row['method'], row['repeat']))
    rng = random.Random(SEED + 1)
    pairs = None
    if os.environ.get('IDCON_PAIRS'):  # revision R1: run only listed (task, method) pairs
        pairs = {(t, m) for t, m in read(os.environ['IDCON_PAIRS'])}
        manifest = [r for r in manifest if any((r['task_id'], m) in pairs for m in methods)]
    schedule = [(r, rep) for r in manifest for rep in range(REPEATS)]
    rng.shuffle(schedule)
    schedule = schedule[worker::workers]
    cache = {}
    OUT.mkdir(parents=True, exist_ok=True)
    with out.open('a', encoding='utf8') as stream:
        for index, (record, repeat) in enumerate(schedule):
            todo = [m for m in methods if (record['task_id'], m, repeat) not in done
                    and (pairs is None or (record['task_id'], m) in pairs)]
            if not todo:
                continue
            identity = read(ROOT / record['identity_file'])
            observed = read(ROOT / record['tables_file'])
            tables = {int(r): v for r, v in observed['role_states'].items()}
            order = list(todo)
            random.Random(hash((record['task_id'], repeat)) & 0xffffffff).shuffle(order)
            for method in order:
                started = time.perf_counter()
                try:
                    answer = dispatch(method, identity, tables, observed['global_state'], BUDGET)
                except Exception as exc:  # retained as a runtime error, never dropped
                    answer = dict(label='UNKNOWN', reason='runtime_error', certificate=False,
                                  mappings=[], detail=f'{type(exc).__name__}: {exc}'[:300])
                elapsed = time.perf_counter() - started
                if elapsed > BUDGET:
                    answer.update(label='UNKNOWN', reason='deadline_overrun', certificate=False)
                keep = {k: answer.get(k) for k in ('label', 'reason', 'certificate', 'mappings',
                                                   'detail', 'native_queries', 'solver_calls')}
                stream.write(json.dumps(dict(task_id=record['task_id'], group_id=record['group_id'],
                                             scenario=record['scenario'], method=method,
                                             repeat=repeat, seconds=elapsed,
                                             outcome=outcome(answer), **keep)) + '\n')
                stream.flush()
            if index % 25 == 0:
                print('W', worker, index, '/', len(schedule), flush=True)


if __name__ == '__main__' and sys.argv[1] not in ('reference', 'generate_focal'):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    parser = argparse.ArgumentParser()
    parser.add_argument('phase')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--worker', type=int, default=0)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--methods')
    args = parser.parse_args()
    if args.phase == 'generate':
        generate(args.limit)
    elif args.phase == 'infer':
        run_shard(args.worker, args.workers,
                  args.methods.split(',') if args.methods else None)


# ---------------------------------------------------------------- reference
def _state_witness(ask, identity, tables, state, budget, binary=None):
    """Exact-state query: exists identity whose aggregate state equals `state`."""
    from projection_engine import Deadline
    end = time.perf_counter() + budget
    upto = {r: [u for u, x in enumerate(v) if x <= state] for r, v in tables.items()}
    kwargs = {} if binary is None else {'binary': binary}
    try:
        if state == 0:
            found = ask(identity, tables, 0, upto, end, **kwargs)
            return ('SAT', found['mapping']) if found else ('UNSAT', None)
        for r, values in sorted(tables.items()):
            restriction = dict(upto)
            restriction[r] = [u for u, x in enumerate(values) if x == state]
            if not restriction[r]:
                continue
            found = ask(identity, tables, 0, restriction, end, **kwargs)
            if found:
                return 'SAT', found['mapping']
        return 'UNSAT', None
    except Deadline:
        return 'UNKNOWN', None
    except (RuntimeError, MemoryError) as exc:  # engine failure, not evidence
        return 'UNKNOWN', None


def reference_task(record, maps):
    from lad_baseline import ask as lad_ask
    from glasgow_baseline import ask as gl_ask, DEFAULT_BINARY
    from coordination_confirmation_data import legal, state_query
    from final_confirmation_evidence import predicate_range
    identity = read(ROOT / record['identity_file'])
    observed = read(ROOT / record['tables_file'])
    tables = {int(r): v for r, v in observed['role_states'].items()}
    possible = predicate_range(observed)
    q = {}
    log = []
    construction = maps.get(record['group_id'])
    for s in range(3):
        if s not in possible:
            q[s] = dict(status='UNSAT', engine='predicate_range')
    if construction is not None and legal(identity, construction):
        s = max([0] + [v[construction[r]] for r, v in tables.items()])
        q[s] = dict(status='SAT', engine='construction_map_replay')
    for s in range(3):
        if s in q:
            continue
        t = time.perf_counter()
        status, mapping = _state_witness(lad_ask, identity, tables, s, 30.)
        log.append(dict(state=s, engine='lad', status=status, seconds=time.perf_counter() - t))
        if status == 'SAT':
            assert legal(identity, mapping)
            q[s] = dict(status='SAT', engine='lad_replayed')
            continue
        if status == 'UNSAT':
            t = time.perf_counter()
            st2, mp2 = _state_witness(
                lambda *a, **k: gl_ask(*a[:5], DEFAULT_BINARY), identity, tables, s, 30.)
            log.append(dict(state=s, engine='glasgow', status=st2, seconds=time.perf_counter() - t))
            assert st2 != 'SAT', ('engine disagreement', record['task_id'], s)
            q[s] = dict(status='UNSAT', engine='lad', corroborated=st2 == 'UNSAT')
            continue
        # (v1 Amendment 2 allowed a further solver here; removed in revision R1, Amendment 4.)
        t = time.perf_counter()
        st2, mp2 = _state_witness(
            lambda *a, **k: gl_ask(*a[:5], DEFAULT_BINARY), identity, tables, s, 60.)
        log.append(dict(state=s, engine='glasgow', status=st2, seconds=time.perf_counter() - t))
        if st2 == 'SAT':
            assert legal(identity, mp2)
            q[s] = dict(status='SAT', engine='glasgow_replayed')
            continue
        if st2 == 'UNSAT':
            q[s] = dict(status='UNSAT', engine='glasgow', corroborated=False)
            continue
        t = time.perf_counter()
        ans = state_query(identity, tables, 0, s, 60.)
        log.append(dict(state=s, engine='cp_sat', status=ans.get('status'), seconds=time.perf_counter() - t))
        if ans.get('status') == 'SAT':
            assert legal(identity, ans['mapping'])
            q[s] = dict(status='SAT', engine='cp_sat_replayed')
        elif ans.get('status') == 'UNSAT':
            q[s] = dict(status='UNSAT', engine='cp_sat', corroborated=False)
        else:
            q[s] = dict(status='UNKNOWN', engine='unresolved')
    sat = [s for s in range(3) if q[s]['status'] == 'SAT']
    unknown = [s for s in range(3) if q[s]['status'] == 'UNKNOWN']
    if not unknown:
        label = ('EMPTY' if not sat else 'SATISFIES' if sat == [0] else
                 'VIOLATES' if sat == [2] else 'UNKNOWN')
        complete = True
    elif 1 in sat or (0 in sat and 2 in sat):
        label, complete = 'UNKNOWN', True
    else:
        label, complete = 'UNASSESSED', False
    return dict(task_id=record['task_id'], label=label, complete=complete,
                states={str(s): q[s] for s in range(3)}, log=log)


def reference_shard(worker, workers):
    mname = os.environ.get('IDCON_MANIFEST', 'manifest.json')
    manifest = read(DATA / mname)[worker::workers]
    maps = read(PRIVATE / 'construction_maps.json')
    out = PRIVATE / (f'references.w{worker}.jsonl' if mname == 'manifest.json' else f'references.{mname[:-5]}.w{worker}.jsonl')
    done = set()
    if os.environ.get('IDCON_RETRY'):
        prior = {}
        for p in sorted(PRIVATE.glob('references*.jsonl')):
            for l in p.read_text().splitlines():
                r = json.loads(l); prior[r['task_id']] = r
        manifest = [m for m in manifest if m['task_id'] in prior and not prior[m['task_id']]['complete']]
        out = PRIVATE / 'references.zretry.jsonl'
        print('RETRY', len(manifest), flush=True)
    if out.exists():
        done = {json.loads(l)['task_id'] for l in out.read_text().splitlines()}
    with out.open('a') as stream:
        for i, record in enumerate(manifest):
            if record['task_id'] in done:
                continue
            row = reference_task(record, maps)
            stream.write(json.dumps(row) + '\n')
            stream.flush()
            print('REF', i, record['task_id'], row['label'], flush=True)


if __name__ == '__main__' and sys.argv[1] == 'reference':
    reference_shard(int(sys.argv[2]), int(sys.argv[3]))


# ---------------------------------------------------------------- amendment 1
# decoy_s proved to be decided by the observation tables alone (a state-S
# identity needs every checked role on an S decoy), so it is kept as a
# predicate-range control and focal_v is added as the V-side scenario.
def generate_focal():
    path = DATA / 'manifest_focal.json'
    assert not path.exists()
    cells = list(itertools.product(FAMILIES, TIERS, CONSTRUCTIONS, VARIANTS))
    ancestors = {a['group_id']: a for a in read(DATA / 'ancestors.json')}
    manifest = []
    for index, (family, (n, k), construction, variant) in enumerate(cells):
        group = f'h_{family}_n{n}_q{k}_{construction}_{variant}'
        identity, checked, selected, g, q, detail = make_ancestor(
            family, n, k, construction, variant, SEED + 1000 + index)
        assert checked == ancestors[group]['checked_roles']
        ipath = DATA / 'identities' / f'{group}.json'
        assert read(ipath)['role_edges'] == json.loads(json.dumps(identity['role_edges']))
        rng = random.Random(SEED + 200000 + index)
        focal = rng.choice(checked)
        radius = rng.choice([1, 2])
        rate = rng.uniform(.05, .6)
        tables = {r: [0] * n for r in checked}
        tables[focal] = [2] * n
        for u in decoys(g, q, selected, focal, radius):
            if rng.random() < rate:
                tables[focal][u] = 0
        task = f'{group}__focal_v'
        tpath = DATA / 'tables' / f'{task}.json'
        dump(tpath, {'role_states': {str(r): v for r, v in tables.items()}, 'global_state': 0})
        manifest.append(dict(task_id=task, group_id=group, family=family, entities=n, roles=k,
                             construction=construction, variant=variant, scenario='focal_v',
                             params=dict(focal_role=focal, radius=radius, decoy_rate=round(rate, 4)),
                             identity_file=ipath.relative_to(ROOT).as_posix(),
                             tables_file=tpath.relative_to(ROOT).as_posix()))
    dump(path, manifest)
    print('FOCAL', len(manifest))


if __name__ == '__main__' and sys.argv[1] == 'generate_focal':
    generate_focal()
