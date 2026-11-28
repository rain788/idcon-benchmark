"""Untouched factorial confirmation of the integrated sole EG-ICAF entry.

The dataset fixes feasible extracted identities without rejecting hard draws.
Inference never parses protected construction maps or references. Source changes
after registration fail closed; append-only predictions can resume by run key.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import itertools
import json
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/final_confirmation'
DATA = ROOT/'data/processed/final_confirmation'
PRIVATE = ROOT/'data/protected/final_confirmation'
SEED = 202611026407
FAMILIES = ['geometric', 'preferential', 'small_world', 'regular', 'erdos', 'articulation_modules']
SCENARIOS = ['all_s', 'all_v', 'single_role_sv', 'single_role_su', 'mixed_suv']
ABLATIONS = ['exact_state_queries', 'no_blocks', 'no_port_capacity', 'no_query_reuse',
             'full_forbidden_cores', 'no_residual_capacity', 'no_permission_completion',
             'no_obligation_filter', 'no_resource_hall']
METHODS = ['eg_icaf', 'whole_cp', 'traditional_cp', 'glasgow', 'lad_direct_early', 'native_lbbd',
           'adaptive_exact_local'] + ABLATIONS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf8')


def prepare():
    from eg_icaf_runtime import prepare_runtime
    prepare_runtime()
    import current_controls, compiled_study, comparison_baselines, glasgow_baseline, lad_direct_baseline


def dispatch(method, identity, tables, base, budget):
    if method == 'eg_icaf':
        from structural_adapter import diagnose_tables
        return diagnose_tables(identity, tables, base, budget)
    if method in ABLATIONS + ['native_lbbd']:
        from current_controls import diagnose
        return diagnose(method, identity, tables, base, budget)
    if method == 'adaptive_exact_local':
        from compiled_study import evaluate
        answer = evaluate(identity, tables, base, 'native_compiled_exact_local', budget)
        stats = answer.pop('stats', {})
        return {**answer, **stats}
    if method == 'glasgow':
        from glasgow_baseline import diagnose_tables
        return diagnose_tables(identity, tables, base, budget)
    if method == 'lad_direct_early':
        from lad_direct_baseline import diagnose_tables
        return diagnose_tables(identity, tables, base, budget, early=True)
    from comparison_baselines import solve
    return solve(method, identity, tables, base, budget)


def pair(family, n, k, construction, anchor_count, seed):
    import networkx as nx
    from submission_data import graph, bfs_nodes
    rng = random.Random(seed)
    g = graph(family, n, seed)
    selected = bfs_nodes(g, rng.randrange(n), k, rng)
    q = g.subgraph(selected).copy()
    if construction == 'forest':
        forest = nx.Graph()
        forest.add_nodes_from(selected)
        for component in nx.connected_components(q):
            forest.add_edges_from(nx.bfs_edges(q, min(component)))
        q = forest
    roles = {u:r for r,u in enumerate(selected)}
    q = nx.relabel_nodes(q, roles)
    anchors = sorted(q, key=lambda r:(-q.degree[r], r))[:anchor_count]
    checks = rng.sample(sorted(set(q)-set(anchors)), min(8, k-anchor_count))
    xyz = [[float(u), float((u*u)%104729), float(u%7)] for u in range(n)]
    identity = dict(candidate_xyz=xyz, candidate_edges=[list(e) for e in sorted(g.edges())],
                    role_count=k, role_edges=[[r,s,None,False] for r,s in sorted(q.edges())],
                    registered_positions={str(r):xyz[selected[r]] for r in anchors},
                    coordinate_tolerance=1e-8, length_tolerance=1e-7, domain_complete=True, injective=True)
    # The extraction map stays protected. It supplies a constructive existence
    # witness, never a domain restriction or shortcut in any timed method.
    return identity, checks, selected, dict(anchor_roles=anchors,
        query_components_after_anchors=nx.number_connected_components(q.subgraph(set(q)-set(anchors))),
        host_blocks_after_anchors=nx.number_connected_components(g.subgraph(set(g)-{selected[r] for r in anchors})),
        query_edges=q.number_of_edges(), host_edges=g.number_of_edges())


def validate():
    import networkx as nx
    from coordination_confirmation_data import legal
    from structural_study import verify
    prepare()
    rng = random.Random(SEED-1)
    checks = []
    # Independent complete permutations cover the new dispatch, every ablation,
    # interval-vs-singleton control, bases and both query construction choices.
    for index in range(18):
        n = 14
        k = 3
        family = FAMILIES[index%len(FAMILIES)]
        identity, checked, known, detail = pair(family, n, k, 'forest' if index%2 else 'induced', index%3, rng.randrange(2**31))
        tables = {r:[rng.randrange(3) for _ in range(n)] for r in checked}
        base = index%3
        assert legal(identity, known)
        states = {max([base]+[v[y[r]] for r,v in tables.items()])
                  for y in itertools.permutations(range(n), k) if legal(identity,y)}
        expected = 'SATISFIES' if states=={0} else 'VIOLATES' if states=={2} else 'UNKNOWN'
        for method in METHODS:
            answer = dispatch(method, identity, tables, base, 5.)
            assert answer['certificate'] and answer['label']==expected, (index,method,states,answer)
            assert verify(identity,tables,base,answer)['passed'], (index,method)
            if method in ['eg_icaf','native_lbbd','adaptive_exact_local']+ABLATIONS:
                assert answer.get('cp_calls',0)==0
            checks.append(dict(case=index, method=method, states=sorted(states), label=answer['label']))
    dump(OUT/'implementation_checks.json', dict(cases=18, checks=len(checks), failures=0,
        source_sha256=sha(Path(__file__)), evidence=checks,
        scope='software development fixtures; no new confirmation input generated or timed'))
    print('VALIDATED', len(checks), flush=True)

    from final_confirmation_evidence import diagnosis, predicate_range, query
    truth_checks = reference_queries = 0
    for statuses in itertools.product(['SAT','UNSAT','UNKNOWN'], repeat=3):
        queries = {str(s):{'status':statuses[s]} for s in range(3)}
        _,_,complete,label = diagnosis(queries)
        if complete:
            for subset in itertools.chain.from_iterable(itertools.combinations(range(3),r) for r in range(4)):
                states = set(subset)
                if any((statuses[s]=='SAT' and s not in states) or (statuses[s]=='UNSAT' and s in states) for s in range(3)):
                    continue
                actual = 'SATISFIES' if states=={0} else 'VIOLATES' if states=={2} else 'UNKNOWN'
                assert actual==label,(statuses,states,label)
                truth_checks += 1
    for case in range(6):
        identity,checked,_,_ = pair(FAMILIES[case],14,3,'induced',case%3,SEED-100-case)
        observed = dict(global_state=case%3,role_states={str(r):[rng.randrange(3) for _ in range(14)] for r in checked})
        truth = {max([observed['global_state']]+[v[y[int(r)]] for r,v in observed['role_states'].items()])
                 for y in itertools.permutations(range(14),3) if legal(identity,y)}
        assert truth<=predicate_range(observed)
        for state in range(3):
            answer = query(identity,observed,state,5.)
            assert answer['status']==('SAT' if state in truth else 'UNSAT')
            reference_queries += 1
    dump(OUT/'reference_checks.json',dict(partial_reference_combinations=27,proved_label_completions=truth_checks,
        independent_cp_permutation_queries=reference_queries,predicate_range_cases=6,failures=0,
        driver_sha256=sha(Path(__file__)),reference_program_sha256=sha(ROOT/'src/final_confirmation_evidence.py')))
    print('REFERENCE CHECKS',truth_checks,reference_queries,flush=True)


def design():
    path = OUT/'design.json'
    if path.exists():
        return check_design()
    assert not (DATA/'manifest.json').exists()
    checks = read(OUT/'implementation_checks.json')
    assert checks['failures']==0 and checks['source_sha256']==sha(Path(__file__))
    public = read(ROOT/'results/innovation_study/public_implementation_freeze.json')
    sources = dict(public['runtime_sources'])
    sources['structural_adapter.py'] = public['public_entry_sha256']
    for name in ['current_controls.py', 'current_control_validate.py', 'compiled_study.py', 'final_confirmation_study.py', 'final_confirmation_evidence.py']:
        sources[name] = sha(ROOT/'src'/name)
    for name,digest in sources.items():
        assert sha(ROOT/'src'/name)==digest, name
    binaries = {name:sha(ROOT/name) for name in [
        'src/native/libeg_icaf_search.so', 'third_party/build/glasgow_subgraph_solver',
        'third_party/build/lad2025_direct/lad2025']}
    p = dict(stage='locally registered before any new confirmation generation, references or timed inference',
        method='EG-ICAF', public_entry='src/structural_adapter.py', seed=SEED,
        public_implementation_freeze_sha256=sha(ROOT/'results/innovation_study/public_implementation_freeze.json'),
        source_hashes=sources, binaries=binaries, implementation_checks_sha256=sha(OUT/'implementation_checks.json'),
        reference_checks_sha256=sha(OUT/'reference_checks.json'),
        hypothesis='Integrated diagnostic obligation/resource interfaces retain end-to-end benefits on new, larger feasible identities; structural module effects and adverse results are retained, not assumed',
        families=FAMILIES, host_sizes=[512,2048], query_sizes=[24,48],
        query_constructions=['forest','induced'], anchor_counts=[0,2], draws_per_cell=1,
        ancestors=96, scenarios=SCENARIOS, tasks=480, methods=METHODS, repeats=2, expected_records=15360,
        checked_roles='eight nonanchor roles uniformly sampled once per ancestor and shared across scenarios',
        observations=dict(all_s='all checked values S',all_v='all checked values V',
            single_role_sv='one checked role independently S/V with P(V)=0.2',
            single_role_su='one checked role independently S/U with P(U)=0.2',
            mixed_suv='all checked roles independently P(S/U/V)=0.6/0.2/0.2'),
        global_state=0, metrics='no metric edges in this new topology scaling stratum; metric correctness remains regression evidence',
        generation='Independent graph per complete factorial cell. BFS-prioritized extraction with seeded disconnected completion, no motif copying, rejection, result-driven replacement or forced diagnostic labels. Both constructions retain a protected feasible map.',
        independent_unit='new sampled graph-pair ancestor; scenarios/repeats dependent; six generator families are not six industrial sources',
        timing='single-thread Linux/WSL, serial randomized method order, 2s cooperative end-to-end budget. Preprocessing, FFI, encoding, search and external startup/I-O timed; disk input and independent replay excluded. Shared-library preparation once outside per-task timing; no pure-kernel ranking claim.',
        budget_seconds=2., method_order_seed=SEED+1,
        controls='all nine current compiled ablations, same-kernel eager LBBD and adaptive exact-local; original exact_state_queries keeps fixed three-target strategy and is not a pure interface control',
        statistical_plan=dict(primary=['lad_direct_early','glasgow','native_lbbd','adaptive_exact_local'],
            endpoint='ancestor-mean PAR-2 milliseconds; unfinished/incorrect applicable run charges 4000ms',
            bootstrap='10000 paired ancestor resamples stratified by generator family',
            tests='100000 paired sign flips of ancestor differences; Holm correction across four primary tests; exchangeability null disclosed',
            seed=SEED+2, ablations='descriptive paired intervals only; no independent-significance claim',
            scaling='report every host-size/query-size/construction/anchor cell and completion counts; no feasibility or performance filtering'),
        references='After prediction freeze, independently replay protected extraction maps and every frozen method positive map (SAT only, verification independent but search provenance disclosed). Unconstrained predicate-rank Cartesian ranges give sound necessary UNSAT certificates. Other exact S/U/V targets use independent whole-map CP-SAT, 15s each; all unresolved states receive one uniform 120s follow-up. Consensus truth is complete from a verified U witness, verified S and V witnesses, or three resolved exact targets. Exact-state and consensus completeness are reported separately. Any unresolved consensus remains in scheduled/coverage denominators and excluded from PAR-2 means; no inference UNSAT borrowed.',
        confirmation_policy='No method, control, generation or split changes after new outcomes. If used for improvement, this entire population becomes exposed; retain its original status and predictions.',
        scope='Synthetic algorithm confirmation only. ERA SHACL applicability audit is separate and contributes zero tasks/sources here; no new industrial input or FEM solve.',
        environment=dict(python=sys.version, platform=platform.platform(),
                         thread_env={k:os.environ.get(k) for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']}))
    dump(path,p)
    print('DESIGN REGISTERED',sha(path),flush=True)
    return p


def check_design():
    p = read(OUT/'design.json')
    for name,digest in p['source_hashes'].items():
        assert sha(ROOT/'src'/name)==digest,name
    for name,digest in p['binaries'].items():
        assert sha(ROOT/name)==digest,name
    assert sha(OUT/'implementation_checks.json')==p['implementation_checks_sha256']
    assert sha(OUT/'reference_checks.json')==p['reference_checks_sha256']
    return p


def generate():
    p = check_design()
    assert not (DATA/'manifest.json').exists(), 'Never regenerate frozen research inputs'
    manifest = []
    ancestors = []
    construction_maps = {}
    products = itertools.product(FAMILIES,p['host_sizes'],p['query_sizes'],p['query_constructions'],p['anchor_counts'])
    for index,(family,n,k,construction,anchor_count) in enumerate(products):
        seed = SEED+1000+index
        gid = f'fc_{family}_n{n}_q{k}_{construction}_a{anchor_count}'
        identity,checked,known,detail = pair(family,n,k,construction,anchor_count,seed)
        ip = DATA/'identities'/(gid+'.json')
        dump(ip,identity)
        construction_maps[gid] = known
        ancestor = dict(group_id=gid, family=family, entities=n, roles=k, construction=construction,
                        anchor_count=anchor_count, seed=seed, checked_roles=checked, **detail)
        ancestors.append(ancestor)
        rng = random.Random(SEED+100000+index)
        for scenario in SCENARIOS:
            tables = {r:[0]*n for r in checked}
            if scenario=='all_v':
                tables = {r:[2]*n for r in checked}
            elif scenario in ['single_role_sv','single_role_su']:
                value = 2 if scenario=='single_role_sv' else 1
                tables[checked[0]] = [value if rng.random()<.2 else 0 for _ in range(n)]
            elif scenario=='mixed_suv':
                tables = {r:rng.choices([0,1,2],weights=[.6,.2,.2],k=n) for r in checked}
            tid = gid+'__'+scenario
            tp = DATA/'tables'/(tid+'.json')
            dump(tp,dict(role_states=tables,global_state=0))
            manifest.append(dict(task_id=tid,group_id=gid,family=family,independent_source=gid,
                                 dataset='synthetic_feasible_factorial',scenario=scenario,
                                 identity_file=ip.relative_to(ROOT).as_posix(), tables_file=tp.relative_to(ROOT).as_posix()))
    assert len(ancestors)==p['ancestors'] and len(manifest)==p['tasks']
    dump(DATA/'ancestors.json',ancestors)
    dump(PRIVATE/'construction_maps.json',construction_maps)
    dump(DATA/'manifest.json',manifest)
    dump(DATA/'input_hashes.json',{r['task_id']:{k:sha(ROOT/r[k]) for k in ['identity_file','tables_file']} for r in manifest})
    print('GENERATED',len(ancestors),'ancestors',len(manifest),'tasks',flush=True)


def freeze():
    p = check_design()
    assert not (OUT/'protocol.json').exists()
    import networkx as nx
    from coordination_confirmation_data import legal
    seen = set()
    construction = read(PRIVATE/'construction_maps.json')
    for r in read(DATA/'manifest.json'):
        if r['group_id'] in seen:
            continue
        assert legal(read(ROOT/r['identity_file']),construction[r['group_id']]),r['group_id']
        seen.add(r['group_id'])
    assert len(seen)==96
    p.update(design_sha256=sha(OUT/'design.json'),manifest_sha256=sha(DATA/'manifest.json'),
             ancestors_sha256=sha(DATA/'ancestors.json'),inputs=read(DATA/'input_hashes.json'),
             private_construction_maps_sha256=sha(PRIVATE/'construction_maps.json'),
             generation_feasibility_checks=len(seen),networkx=nx.__version__)
    dump(OUT/'protocol.json',p)
    for name,digest in p['source_hashes'].items():
        source = ROOT/'src'/name
        snapshot = OUT/'source_snapshot'/name
        snapshot.parent.mkdir(parents=True,exist_ok=True)
        snapshot.write_bytes(source.read_bytes())
        assert sha(snapshot)==digest
    print('FROZEN',len(p['inputs']),'tasks',sha(OUT/'protocol.json'),flush=True)


def check():
    p = read(OUT/'protocol.json')
    check_design()
    assert sha(OUT/'design.json')==p['design_sha256']
    assert sha(DATA/'manifest.json')==p['manifest_sha256']
    assert sha(DATA/'ancestors.json')==p['ancestors_sha256']
    for r in read(DATA/'manifest.json'):
        for k,digest in p['inputs'][r['task_id']].items():
            assert sha(ROOT/r[k])==digest,(r['task_id'],k)
    return p


def infer():
    p = check()
    prepare()
    path = OUT/'predictions.jsonl'
    frozen = OUT/'prediction_freeze.json'
    if frozen.exists():
        assert sha(path)==read(frozen)['sha256']
        return
    done = set()
    if path.exists():
        done = {(r['task_id'],r['method'],r['repeat']) for r in map(json.loads,path.read_text(encoding='utf8').splitlines())}
    rng = random.Random(p['method_order_seed'])
    with path.open('a',encoding='utf8') as output:
        for index,row in enumerate(read(DATA/'manifest.json')):
            identity = read(ROOT/row['identity_file'])
            observed = read(ROOT/row['tables_file'])
            tables = {int(r):v for r,v in observed['role_states'].items()}
            for repeat in range(p['repeats']):
                names = METHODS.copy()
                rng.shuffle(names)
                for method in names:
                    key = row['task_id'],method,repeat
                    if key in done:
                        continue
                    launches = [0]
                    old_run = subprocess.run
                    def tracked(*args,**kwargs):
                        launches[0] += 1
                        return old_run(*args,**kwargs)
                    subprocess.run = tracked
                    start = time.perf_counter()
                    try:
                        answer = dispatch(method,identity,tables,observed['global_state'],p['budget_seconds'])
                    except Exception as exc:
                        # Retain runtime failures as penalized observations;
                        # never replace a difficult input or silently retry it.
                        answer = dict(label='UNKNOWN',reason='runtime_error',certificate=False,mappings=[],
                                      runtime_error=type(exc).__name__+': '+str(exc))
                    finally:
                        subprocess.run = old_run
                    elapsed = time.perf_counter()-start
                    if elapsed>p['budget_seconds']:
                        answer.update(label='UNKNOWN',reason='deadline_overrun',certificate=False)
                    if method in ['eg_icaf','native_lbbd','adaptive_exact_local']+ABLATIONS:
                        assert answer.get('cp_calls',0)==0 and launches[0]==0,(key,'native delegation')
                    output.write(json.dumps({**row,**answer,'seconds':elapsed,'method':method,'repeat':repeat,
                                             'external_process_launches':launches[0]})+'\n')
                    output.flush()
                    done.add(key)
            if (index+1)%5==0:
                print('TIMED',index+1,'/',p['tasks'],'records',len(done),flush=True)
    assert len(done)==p['expected_records']
    dump(frozen,dict(rows=len(done),sha256=sha(path),protocol_sha256=sha(OUT/'protocol.json')))
    print('PREDICTIONS FROZEN',len(done),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase',choices=['validate','design','generate','freeze','check','infer'])
    args = parser.parse_args()
    {'validate':validate,'design':design,'generate':generate,'freeze':freeze,'check':check,'infer':infer}[args.phase]()
