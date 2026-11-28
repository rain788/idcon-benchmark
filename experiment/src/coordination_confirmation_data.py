"""Frozen, method-blind synthetic confirmation assets and independent references.

No EG-ICAF code, predictions, or candidate propagation is used here.  All input
graphs and unary observations are constructed; no engineering/FEM source added.
"""
import argparse
import copy
import hashlib
import itertools
import json
import random
import time
from pathlib import Path

import networkx as nx
import numpy as np
from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT/'data/processed/coordination_confirmation'
PRIVATE = ROOT/'data/protected/coordination_confirmation'
OUT = ROOT/'results/coordination_confirmation'
SEED = 202611021337
FAMILIES = ['connected_general', 'multiport_blocks', 'partial_sharing', 'mixed_blocks']
SCENARIOS = ['all_s', 'all_v', 'missing_or_ambiguous', 'resource_or_edge_deficit']


def dump(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')


def read(p):
    return json.loads(p.read_text(encoding='utf8'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def random_shape(rng, n, chord_rate):
    g = nx.Graph(); g.add_nodes_from(range(n))
    for u in range(1, n):
        g.add_edge(u, rng.randrange(u))
    for u, v in itertools.combinations(range(n), 2):
        if rng.random() < chord_rate:
            g.add_edge(u, v)
    return g


def make_pair(family, index, rng):
    q = nx.Graph(); q.add_edge(0, 1)
    count = 1 if family == 'connected_general' else rng.randint(2, 4)
    sizes = [rng.randint(8, 16)] if count == 1 else [rng.randint(4, 6) for _ in range(count)]
    pieces = []
    for size in sizes:
        h = random_shape(rng, size, rng.uniform(.04, .22))
        nodes = list(range(len(q), len(q)+size))
        h = nx.relabel_nodes(h, dict(zip(h, nodes)))
        q.add_edges_from(h.edges); q.add_nodes_from(h)
        # Independently sampled nonempty boundary signatures and port counts.
        for anchor in (0, 1):
            for u in rng.sample(nodes, rng.randint(1, min(3, size))):
                q.add_edge(anchor, u)
        pieces.append(nodes)
    g = q.copy()
    # Additional copies retain genuine alternative embeddings, rather than only
    # permuting one structure. Every ancestor samples fresh random topology.
    copies = rng.randint(1, 2)
    for _ in range(copies):
        for nodes in pieces:
            mapping = {u: len(g)+j for j, u in enumerate(nodes)}
            g.add_nodes_from(mapping.values())
            g.add_edges_from((mapping[u], mapping[v]) for u, v in q.subgraph(nodes).edges)
            for a in (0, 1):
                g.add_edges_from((a, mapping[u]) for u in nodes if q.has_edge(a, u))
    free = list(set(g)-{0, 1})
    if family in ('connected_general', 'partial_sharing'):
        comps = list(nx.connected_components(g.subgraph(free)))
        for left, right in zip(comps, comps[1:]):
            g.add_edge(rng.choice(sorted(left)), rng.choice(sorted(right)))
        # Partial sharing has one host block, several query components, and
        # cross-component alternative paths sampled independently.
        for _ in range(len(free)//3):
            u, v = rng.sample(free, 2); g.add_edge(u, v)
    elif family == 'mixed_blocks':
        comps = list(nx.connected_components(g.subgraph(free)))
        for j in range(0, len(comps)-1, 2):
            g.add_edge(rng.choice(sorted(comps[j])), rng.choice(sorted(comps[j+1])))
    # Non-isomorphic distractor attachment shapes and chords vary by ancestor.
    for _ in range(rng.randint(3, 9)):
        u = len(g); g.add_edge(u, rng.choice(list(set(g)-{0, 1})))
        if rng.random() < .35:
            g.add_edge(u, rng.choice(list(set(g)-{u})))
    assert len(g) <= 100 and 8 <= len(q) <= 30
    xyz = [[rng.uniform(-20, 20), rng.uniform(-20, 20), float(u)] for u in g]
    # Role 0/2 are ordinary free roles; anchors are always role 1/3.
    order = [2, 0, 3, 1]+list(range(4, len(q)))
    role = {u: r for r, u in enumerate(order)}
    perm = list(g); rng.shuffle(perm); candidate = {u: i for i, u in enumerate(perm)}
    metric = index % 4 == 3
    edges = []
    for u, v in q.edges:
        length = float(np.linalg.norm(np.asarray(xyz[u])-xyz[v])) if metric and rng.random() < .25 else None
        edges.append([role[u], role[v], length, False])
    identity = dict(family='controlled_synthetic_confirmation',
        candidate_xyz=[xyz[u] for u in perm],
        candidate_edges=[[candidate[u], candidate[v]] for u, v in g.edges],
        role_count=len(q), role_edges=edges,
        registered_positions={'1': xyz[0], '3': xyz[1]},
        coordinate_tolerance=1e-7, length_tolerance=1e-6,
        domain_complete=True, injective=True)
    known = [candidate[u] for u in order]
    return identity, known


def structural_graph(identity):
    """Pair fingerprint includes role/anchor labels and both graph structures."""
    h = nx.Graph()
    for r in range(identity['role_count']):
        h.add_node(('q', r), color='q_anchor_'+str(r) if str(r) in identity['registered_positions'] else 'q_free')
    for u in range(len(identity['candidate_xyz'])):
        anchor = next((r for r, p in identity['registered_positions'].items() if p == identity['candidate_xyz'][u]), None)
        h.add_node(('g', u), color='g_anchor_'+anchor if anchor is not None else 'g_free')
    h.add_edges_from((('q', r), ('q', s)) for r, s, _, _ in identity['role_edges'])
    h.add_edges_from((('g', u), ('g', v)) for u, v in identity['candidate_edges'])
    return h


def generate():
    if (PUBLIC/'manifest.json').exists():
        raise FileExistsError('Confirmation inputs already exist; refuse to regenerate frozen assets')
    design = dict(seed=SEED, created='2026-11-02', source='controlled synthetic topology and unary observations',
        new_fem_solves=0, new_industrial_sources=0,
        families=FAMILIES, ancestors_per_family=8, scenarios=SCENARIOS,
        checked_role_counts=[2, 4, 8], checked_role_rule='2,4,8 cyclic by ancestor index; anchors excluded',
        generation='independent random recursive trees and chords, boundary signatures, copied host alternatives and distractor attachments; one draw per ancestor; no method predictions read',
        scenario_rules=dict(all_s='all checked values S', all_v='all checked values V',
            missing_or_ambiguous='even index: one missing-evidence predicate; odd index: one independently sampled S/V predicate with planted S entry',
            resource_or_edge_deficit='even index: remove every non-anchor edge at fixed anchor 1; odd index: independently delete 20 percent of host edges'),
        metric_rule='ancestor index modulo four equals three: each query edge gets its planted length with probability .25',
        reference='three independent whole-map CP-SAT state queries, 3 seconds each; no EG-ICAF propagation/decomposition; SAT maps replayed',
        statistics_unit='ancestor; scenes and timing repeats are dependent; families remain constructed mechanisms',
        split='confirmation only, never used to develop/choose optimization',
        scope_limit='No claim of natural requirements, industrial/FEM validity, or independent population sampling; shared generation families induce dependence',
        physical_adapter='Not used: native arbitrary unary tables cannot in general be represented by the role-0 single-load/role-2 observation adapter')
    dump(PUBLIC/'design.json', design)
    rng = random.Random(SEED); records = []; ancestors = []; graphs = []; knowns = {}
    for family in FAMILIES:
        for index in range(8):
            gid = f'cc_{family}_{index:02d}'
            identity, known = make_pair(family, index, rng)
            h = structural_graph(identity)
            for oldid, old in graphs:
                assert not nx.is_isomorphic(h, old, node_match=nx.algorithms.isomorphism.categorical_node_match('color', None)), (gid, oldid)
            graphs.append((gid, h)); knowns[gid] = known
            free = [r for r in range(identity['role_count']) if r not in (1, 3)]
            checked = [0, 2]+rng.sample([r for r in free if r not in (0, 2)], [2, 4, 8][index % 3]-2)
            ancestor = dict(group_id=gid, template_id=gid, family=family, dataset='new_confirmation',
                split='confirmation', role_count=identity['role_count'], candidates=len(identity['candidate_xyz']),
                checked_roles=checked, host_blocks=nx.number_connected_components(nx.Graph(h.subgraph([n for n in h if n[0]=='g' and h.nodes[n]['color']=='g_free']))),
                structural_pair_wl=nx.weisfeiler_lehman_graph_hash(h, node_attr='color'),
                source='controlled synthetic; no FEM or industrial source')
            ancestors.append(ancestor)
            for scene in SCENARIOS:
                i = copy.deepcopy(identity); n = len(i['candidate_xyz'])
                tables = {r: [0]*n for r in checked}
                if scene == 'all_v':
                    tables = {r: [2]*n for r in checked}
                elif scene == 'missing_or_ambiguous':
                    if index % 2 == 0:
                        tables[checked[0]] = [1]*n
                    else:
                        tables[checked[0]] = [rng.choice([0, 2]) for _ in range(n)]
                        tables[checked[0]][known[checked[0]]] = 0
                elif scene == 'resource_or_edge_deficit':
                    if index % 2 == 0:
                        a = known[1]; other = known[3]
                        i['candidate_edges'] = [[u, v] for u, v in i['candidate_edges'] if a not in (u, v) or other in (u, v)]
                    else:
                        i['candidate_edges'] = [[u, v] for u, v in i['candidate_edges'] if rng.random() >= .2]
                tid = gid+'__'+scene
                ip = PUBLIC/'identities'/f'{tid}.json'; tp = PUBLIC/'tables'/f'{tid}.json'
                dump(ip, i); dump(tp, dict(role_states=tables, global_state=0))
                records.append({**ancestor, 'task_id': tid, 'scenario': scene,
                    'identity_file': ip.relative_to(ROOT).as_posix(), 'tables_file': tp.relative_to(ROOT).as_posix()})
    dump(PUBLIC/'ancestors.json', ancestors); dump(PUBLIC/'manifest.json', records)
    dump(PUBLIC/'input_hashes.json', {r['task_id']: dict(identity=sha(ROOT/r['identity_file']), tables=sha(ROOT/r['tables_file'])) for r in records})
    dump(PUBLIC/'template_checks.json', dict(ancestors=32, exact_structural_pair_classes=len(graphs), duplicates=0,
        comparison='exact pair-graph colored isomorphism; ignores metric values and observes structural novelty only',
        independent_population_claim=False))
    dump(PRIVATE/'planted_mappings.json', knowns)
    dump(ROOT/'data/splits/coordination_confirmation.json', ancestors)
    dump(ROOT/'data/catalog/15_协调优化确认/dataset.json', dict(name='协调优化确认',
        data_nature='controlled synthetic', ancestors=32, tasks=128, new_fem_solves=0,
        manifest='data/processed/coordination_confirmation/manifest.json',
        reference='data/protected/coordination_confirmation/task_reference.json',
        split='data/splits/coordination_confirmation.json', purpose='new frozen confirmation, not development'))
    print('GENERATED', len(ancestors), len(records), flush=True)


def legal(identity, y):
    if len(y) != identity['role_count'] or len(set(y)) != len(y): return False
    xyz = np.asarray(identity['candidate_xyz'])
    if any(not 0 <= u < len(xyz) for u in y): return False
    for _r, _v in identity.get('role_domains', {}).items():
        if y[int(_r)] not in set(_v): return False
    for r, p in identity['registered_positions'].items():
        if max(abs(xyz[y[int(r)]]-p)) >= identity['coordinate_tolerance']: return False
    edges = {frozenset(e) for e in identity['candidate_edges']}
    return all(frozenset((y[r], y[s])) in edges and (length is None or abs(np.linalg.norm(xyz[y[r]]-xyz[y[s]])-length) < identity['length_tolerance']) for r,s,length,_ in identity['role_edges'])


def state_query(identity, tables, base, state, budget=3.):
    start = time.perf_counter(); end = start+budget
    n = len(identity['candidate_xyz']); q = identity['role_count']; xyz = np.asarray(identity['candidate_xyz'])
    m = cp_model.CpModel(); ys = [m.new_int_var(0,n-1,f'y{r}') for r in range(q)]
    for _r, _v in identity.get('role_domains', {}).items():
        m.add_allowed_assignments([ys[int(_r)]], [[u] for u in sorted(_v)])
    m.add_all_different(ys)
    for r, point in identity['registered_positions'].items():
        matches = [u for u in range(n) if max(abs(xyz[u]-point)) < identity['coordinate_tolerance']]
        assert len(matches) == 1; m.add(ys[int(r)] == matches[0])
    for r, s, length, _ in identity['role_edges']:
        pairs = [(u,v) for a,b in identity['candidate_edges'] for u,v in ((a,b),(b,a)) if length is None or abs(np.linalg.norm(xyz[u]-xyz[v])-length) < identity['length_tolerance']]
        m.add_allowed_assignments([ys[r],ys[s]],pairs)
    vs = []
    for r, values in tables.items():
        p = m.new_int_var(0,2,f'p{r}'); m.add_element(ys[r],values,p); vs.append(p)
    t = m.new_int_var(0,2,'state'); m.add_max_equality(t,vs+[base]); m.add(t==state)
    remain=end-time.perf_counter()
    if remain <= 0: return dict(status='UNKNOWN', seconds=time.perf_counter()-start, mapping=None)
    solver=cp_model.CpSolver(); solver.parameters.num_search_workers=1
    solver.parameters.random_seed=71933; solver.parameters.max_time_in_seconds=remain
    status=solver.solve(m)
    y=[solver.value(v) for v in ys] if status in (cp_model.OPTIMAL,cp_model.FEASIBLE) else None
    if y is not None:
        assert legal(identity,y) and max([base]+[values[y[r]] for r,values in tables.items()])==state
    return dict(status='SAT' if y is not None else ('UNSAT' if status==cp_model.INFEASIBLE else 'UNKNOWN'),
        seconds=time.perf_counter()-start,mapping=y)


def tiny_checks():
    rng=random.Random(882713); checks=[]
    for case in range(12):
        n=6; q=4; xyz=[[float(u),float(u*u),0.] for u in range(n)]
        i=dict(candidate_xyz=xyz,candidate_edges=[[u,v] for u,v in itertools.combinations(range(n),2) if rng.random()<.45],role_count=q,
            role_edges=[[r,s,None,False] for r,s in itertools.combinations(range(q),2) if rng.random()<.5],
            registered_positions={'1':xyz[1]},coordinate_tolerance=1e-7,length_tolerance=1e-7,domain_complete=True,injective=True)
        tables={r:[rng.randrange(3) for _ in range(n)] for r in (0,2,3)}
        truth={max(values[y[r]] for r,values in tables.items()) for y in itertools.permutations(range(n),q) if legal(i,y)}
        cpstates={s for s in range(3) if state_query(i,tables,0,s)['status']=='SAT'}
        assert truth==cpstates
        checks.append(dict(case=case,permutation_states=sorted(truth),cp_states=sorted(cpstates),passed=True))
    dump(PRIVATE/'reference_unit_checks.json',dict(cases=12,passed=12,checks=checks,scope='implementation checks, not research samples'))


def reference():
    assert not (PRIVATE/'task_reference.json').exists(), 'Refuse to overwrite frozen references'
    tiny_checks(); records=read(PUBLIC/'manifest.json'); refs=[]
    for j,r in enumerate(records):
        identity=read(ROOT/r['identity_file']); observed=read(ROOT/r['tables_file'])
        tables={int(k):v for k,v in observed['role_states'].items()}; base=observed['global_state']
        queries={str(s):state_query(identity,tables,base,s) for s in range(3)}
        states=[s for s in range(3) if queries[str(s)]['status']=='SAT']; complete=all(x['status']!='UNKNOWN' for x in queries.values())
        label=('SATISFIES' if states==[0] else 'VIOLATES' if states==[2] else 'UNKNOWN') if complete else 'UNASSESSED'
        reason='identity_inconsistent' if not states else 'missing_evidence_witness' if 1 in states else 'conflicting_identity_witnesses' if len(states)>1 else 'counterexample_excluded'
        refs.append(dict(task_id=r['task_id'],group_id=r['group_id'],states=states,complete=complete,reference_label=label,reference_reason=reason,queries=queries))
        if (j+1)%8==0: print('REFERENCES',j+1,len(records),flush=True)
    dump(PRIVATE/'task_reference.json',refs)
    dump(PRIVATE/'reference_freeze.json',dict(reference_sha256=sha(PRIVATE/'task_reference.json'),
        manifest_sha256=sha(PUBLIC/'manifest.json'),inputs_sha256=sha(PUBLIC/'input_hashes.json'),
        generator_sha256=sha(Path(__file__)),complete=sum(r['complete'] for r in refs),total=len(refs),
        independent_reference='monolithic whole-map three-state CP; SAT maps independently replayed; ordinary UNSAT trusted'))
    print('REFERENCE COMPLETE',sum(r['complete'] for r in refs),len(refs),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['generate','reference']);globals()[p.parse_args().phase]()
