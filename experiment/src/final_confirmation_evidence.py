"""Independent references, strict scoring and preregistered paired analysis.

No reference or scoring routine is called by timed inference. Constructive
positive maps are replayed against original relations; inference UNSAT is never
borrowed. General reference CP UNSAT is trusted, not a formal proof log.
"""
import argparse
from collections import Counter, defaultdict
import csv
import itertools
import json
from pathlib import Path
import statistics
import time

from final_confirmation_study import ROOT, OUT, DATA, PRIVATE, sha, read, dump, check


def replay(identity, observed, mapping):
    # This checker reconstructs all original hard relations, independent of EG
    # domains, decomposition, propagation and learned clauses.
    from coordination_confirmation_data import legal
    if not legal(identity,mapping):
        return None
    return max([observed['global_state']]+[v[mapping[int(r)]] for r,v in observed['role_states'].items()])


def query(identity, observed, target, budget):
    from coordination_confirmation_data import state_query
    tables = {int(r):v for r,v in observed['role_states'].items()}
    answer = state_query(identity,tables,observed['global_state'],target,budget)
    if answer['status']=='SAT':
        assert replay(identity,observed,answer['mapping'])==target
    return answer


def predicate_range(observed):
    possible = {observed['global_state']}
    for values in observed['role_states'].values():
        possible = {max(a,b) for a in possible for b in set(values)}
    return possible


def diagnosis(queries):
    states = [s for s in range(3) if queries[str(s)]['status']=='SAT']
    exact = all(queries[str(s)]['status']!='UNKNOWN' for s in range(3))
    complete = exact or 1 in states or (0 in states and 2 in states)
    label = ('SATISFIES' if states==[0] else 'VIOLATES' if states==[2] else 'UNKNOWN') if complete else 'UNASSESSED'
    return states, exact, complete, label


def reference():
    p = check()
    frozen = read(OUT/'prediction_freeze.json')
    predictions = OUT/'predictions.jsonl'
    assert sha(predictions)==frozen['sha256'] and frozen['rows']==p['expected_records']
    assert sha(PRIVATE/'construction_maps.json')==p['private_construction_maps_sha256']
    construction = read(PRIVATE/'construction_maps.json')
    by_task = defaultdict(list)
    for line in predictions.open(encoding='utf8'):
        a = json.loads(line)
        by_task[a['task_id']].extend(a.get('mappings',[]))
    output = PRIVATE/'references.jsonl'
    if (PRIVATE/'reference_freeze.json').exists():
        assert sha(output)==read(PRIVATE/'reference_freeze.json')['sha256']
        return
    done = {a['task_id'] for a in map(json.loads,output.read_text(encoding='utf8').splitlines())} if output.exists() else set()
    with output.open('a',encoding='utf8') as stream:
        for index,row in enumerate(read(DATA/'manifest.json')):
            if row['task_id'] in done:
                continue
            identity = read(ROOT/row['identity_file'])
            observed = read(ROOT/row['tables_file'])
            # Ignoring hard graph relations can only enlarge the state range.
            possible = predicate_range(observed)
            queries = {str(s):dict(status='UNSAT' if s not in possible else 'UNKNOWN',
                method='unconstrained_predicate_range' if s not in possible else 'unresolved',mapping=None) for s in range(3)}
            witness_sources = Counter()
            source_maps = [('source_extraction',construction[row['group_id']])]+[('frozen_method_positive',y) for y in by_task[row['task_id']]]
            seen = set()
            for source,mapping in source_maps:
                key = tuple(mapping)
                if key in seen:
                    continue
                seen.add(key)
                state = replay(identity,observed,mapping)
                assert state is not None, (row['task_id'],source,'invalid positive map')
                witness_sources[source] += 1
                if queries[str(state)]['status']!='SAT':
                    assert queries[str(state)]['status']!='UNSAT'
                    queries[str(state)] = dict(status='SAT',method=source,mapping=mapping)
            attempts = []
            for budget in [15.,120.]:
                for state in range(3):
                    if queries[str(state)]['status']!='UNKNOWN':
                        continue
                    a = query(identity,observed,state,budget)
                    attempts.append(dict(state=state,budget_seconds=budget,**a))
                    if a['status']!='UNKNOWN':
                        queries[str(state)] = {**a,'method':'independent_whole_cp'}
            states,exact,complete,label = diagnosis(queries)
            stream.write(json.dumps(dict(task_id=row['task_id'],queries=queries,states=states,
                exact_state_complete=exact,complete=complete,reference_label=label,
                positive_witness_sources=dict(witness_sources),attempts=attempts))+'\n')
            stream.flush()
            done.add(row['task_id'])
            if (index+1)%5==0:
                print('REFERENCED',index+1,'/',p['tasks'],flush=True)
    assert len(done)==p['tasks']
    dump(PRIVATE/'reference_freeze.json',dict(rows=len(done),sha256=sha(output),protocol_sha256=sha(OUT/'protocol.json'),
        prediction_sha256=frozen['sha256'],scope='independently verified constructive SAT and necessary range proofs, otherwise independent CP search; solver UNSAT trusted'))


def score():
    p = check()
    prediction = read(OUT/'prediction_freeze.json')
    reference = read(PRIVATE/'reference_freeze.json')
    assert sha(OUT/'predictions.jsonl')==prediction['sha256']
    assert sha(PRIVATE/'references.jsonl')==reference['sha256']
    refs = {a['task_id']:a for a in map(json.loads,(PRIVATE/'references.jsonl').read_text(encoding='utf8').splitlines())}
    data = {r['task_id']:(read(ROOT/r['identity_file']),read(ROOT/r['tables_file'])) for r in read(DATA/'manifest.json')}
    from structural_study import verify
    rows = []
    bad = []
    maps = halls = alloc = 0
    seen = set()
    for line in (OUT/'predictions.jsonl').open(encoding='utf8'):
        a = json.loads(line)
        key = a['task_id'],a['method'],a['repeat']
        assert key not in seen,key
        seen.add(key)
        identity,observed = data[a['task_id']]
        truth = refs[a['task_id']]
        states = [replay(identity,observed,y) for y in a.get('mappings',[])]
        valid = all(s is not None for s in states)
        verification = verify(identity,{int(r):v for r,v in observed['role_states'].items()},observed['global_state'],a)
        valid &= verification['passed']
        maps += len(states)
        halls += verification['hall_certificates_checked']
        alloc += verification['allocation_hall_checked']
        reason = a['reason']
        ok = ((reason=='identity_inconsistent' and truth['exact_state_complete'] and not truth['states'] and not states)
              or (reason=='missing_evidence_witness' and 1 in states)
              or (reason=='conflicting_identity_witnesses' and len(set(states))>1)
              or (reason=='counterexample_excluded' and truth['complete'] and truth['reference_label'] in ['SATISFIES','VIOLATES'] and bool(states)))
        assessed = truth['complete']
        completed = bool(assessed and a['certificate'] and valid and ok and a['label']==truth['reference_label'] and a['seconds']<=p['budget_seconds'])
        contradiction = ((a['label']=='SATISFIES' and any(s!=0 for s in truth['states'])) or
                         (a['label']=='VIOLATES' and any(s!=2 for s in truth['states'])) or
                         (reason=='identity_inconsistent' and bool(truth['states'])))
        if not valid or (a['certificate'] and (contradiction or (assessed and not completed))):
            bad.append(dict(key=key,valid=valid,reason=reason,reference=truth['reference_label']))
        par2 = 1000*(a['seconds'] if completed else 2*p['budget_seconds']) if assessed else None
        rows.append(dict(task_id=a['task_id'],group_id=a['group_id'],family=a['family'],scenario=a['scenario'],
            method=a['method'],repeat=a['repeat'],seconds=a['seconds'],label=a['label'],reason=reason,
            assessed=assessed,exact_state_complete=truth['exact_state_complete'],completed=completed,par2_ms=par2,
            external_process_launches=a['external_process_launches'],local_calls=a.get('local_oracle_calls',0),
            resource_cuts=a.get('resource_cuts_learned',0),allocation_hall_cuts=a.get('allocation_hall_cuts',0),
            block_coordination=a.get('block_coordination',False),compiled_search_calls=a.get('compiled_search_calls',0)))
    assert len(rows)==p['expected_records']
    path = OUT/'scored.csv'
    with path.open('w',encoding='utf8',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = []
    for method in p['methods']:
        xs = [r for r in rows if r['method']==method]
        units = defaultdict(list)
        for r in xs:
            if r['assessed']:
                units[r['group_id']].append(r['par2_ms'])
        summary.append(dict(method=method,runs=len(xs),assessed=sum(r['assessed'] for r in xs),
            completed=sum(r['completed'] for r in xs),par2_ms=statistics.mean(statistics.mean(v) for v in units.values()) if units else None))
    result = dict(records=len(rows),failures=bad,positive_maps_replayed=maps,hall_certificates_replayed=halls,
        allocation_hall_certificates_replayed=alloc,reference_tasks=len(refs),consensus_reference_complete=sum(r['complete'] for r in refs.values()),
        exact_state_reference_complete=sum(r['exact_state_complete'] for r in refs.values()),summaries=summary,
        prediction_sha256=prediction['sha256'],reference_sha256=reference['sha256'],scored_sha256=sha(path),
        scope='new synthetic factorial confirmation of the frozen integrated implementation; no industrial or natural-requirement claim')
    dump(OUT/'summary.json',result)
    print(json.dumps(result),flush=True)
    assert not bad


def analysis():
    import numpy as np
    p = check()
    summary = read(OUT/'summary.json')
    assert sha(OUT/'scored.csv')==summary['scored_sha256'] and not summary['failures']
    rows = list(csv.DictReader((OUT/'scored.csv').open(encoding='utf8',newline='')))
    groups = defaultdict(list)
    for r in rows:
        if r['assessed']=='True':
            groups[r['method'],r['group_id']].append(float(r['par2_ms']))
    ancestors = {r['group_id']:r for r in read(DATA/'ancestors.json')}
    ids = sorted(g for m,g in groups if m=='eg_icaf')
    assert ids, 'No complete consensus reference: do not fabricate a ranking'
    rng = np.random.default_rng(p['statistical_plan']['seed'])
    comparisons = []
    for method in p['methods']:
        if method=='eg_icaf':
            continue
        assert ids==sorted(g for m,g in groups if m==method)
        delta = np.array([statistics.mean(groups['eg_icaf',g])-statistics.mean(groups[method,g]) for g in ids])
        draws = np.zeros(10000)
        for family in p['families']:
            values = delta[[j for j,g in enumerate(ids) if ancestors[g]['family']==family]]
            if len(values):
                draws += rng.choice(values,(10000,len(values)),replace=True).sum(axis=1)/len(ids)
        lower,upper = np.quantile(draws,[.025,.975])
        test = None
        if method in p['statistical_plan']['primary']:
            observed = abs(float(delta.mean()))
            extreme = 0
            for _ in range(100):
                signed = rng.choice([-1,1],(1000,len(delta)))*delta
                extreme += int(np.sum(np.abs(signed.mean(axis=1))>=observed))
            test = (1+extreme)/100001
        comparisons.append(dict(control=method,ancestors=len(ids),difference_ms=float(delta.mean()),
            interval_ms=[float(lower),float(upper)],wins=int(np.sum(delta<0)),median_ms=float(np.median(delta)),
            signflip_p=test,scope='primary Holm family' if test is not None else 'descriptive ablation/secondary'))
    primary = sorted([x for x in comparisons if x['signflip_p'] is not None],key=lambda x:x['signflip_p'])
    adjusted = 0
    for j,x in enumerate(primary):
        adjusted = max(adjusted,min(1.,(len(primary)-j)*x['signflip_p']))
        x['holm_p'] = adjusted
    cells = []
    for n,k,c,a in itertools.product(p['host_sizes'],p['query_sizes'],p['query_constructions'],p['anchor_counts']):
        for method in p['methods']:
            xs = [r for r in rows if r['method']==method and
                  (ancestors[r['group_id']]['entities'],ancestors[r['group_id']]['roles'],ancestors[r['group_id']]['construction'],ancestors[r['group_id']]['anchor_count'])==(n,k,c,a)]
            assessed = [float(r['par2_ms']) for r in xs if r['assessed']=='True']
            cells.append(dict(entities=n,roles=k,construction=c,anchors=a,method=method,runs=len(xs),
                assessed=len(assessed),completed=sum(r['completed']=='True' for r in xs),par2_ms=statistics.mean(assessed) if assessed else None))
    dump(OUT/'paired_statistics.json',dict(contrasts=comparisons,factorial_cells=cells,
        scored_sha256=sha(OUT/'scored.csv'),protocol_sha256=sha(OUT/'protocol.json'),
        caution='Randomization sign-flip null requires exchangeability. Six synthetic families and repeat/scenario counts do not establish industrial or cross-domain generalization.'))
    print(json.dumps(dict(contrasts=comparisons,cells=len(cells))),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase',choices=['reference','score','analysis'])
    args = parser.parse_args()
    {'reference':reference,'score':score,'analysis':analysis}[args.phase]()
