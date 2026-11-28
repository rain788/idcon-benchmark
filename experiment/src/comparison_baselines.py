"""Named, equal-semantics baseline implementations for the final comparison.

Traditional CP is OR-Tools original CP Solver (pywrapcp), not CP-SAT.
LBBD is a local feasibility LBBD with fully exposed ownership decisions and
unminimized forbidden-assignment cuts. It is not an external LBBD package.
"""
import math, time
import numpy as np
from ortools.constraint_solver import pywrapcp
from semantic_projection import Projection, ResourceLimit
from projection_engine import guard, graph_data, Deadline, Unsupported
from full_benchmark_methods import consensus, rank_of, run

def traditional_query(identity,tables,base,allowed,end):
    guard(end);g,q,a=graph_data(identity);xyz=np.asarray(identity['candidate_xyz'])
    cp=pywrapcp.Solver('Traditional CP: original OR-Tools CP Solver')
    domains={r:sorted({a[r]} if r in a else {u for u in g if u not in a.values() and g.degree[u]>=q.degree[r]}) for r in q}
    for _r,_v in {int(_r):set(_v) for _r,_v in identity.get('role_domains',{}).items()}.items():domains[_r]=sorted(set(domains[_r])&_v)
    if any(not d for d in domains.values()):return None
    ys={r:cp.IntVar(domains[r],str(r)) for r in q}
    cp.Add(cp.AllDifferent(list(ys.values()),True))
    for r,s,length,_ in identity['role_edges']:
        guard(end)
        pairs=[(u,v) for u in domains[r] for v in g[u] if v in domains[s] and (length is None or abs(np.linalg.norm(xyz[u]-xyz[v])-length)<identity['length_tolerance'])]
        if not pairs:return None
        cp.Add(cp.AllowedAssignments([ys[r],ys[s]],pairs))
    if set(allowed)!={0,1,2}:
        states=[cp.Element(list(v),ys[r]).Var() for r,v in tables.items()]
        aggregate=cp.Max([cp.IntConst(base)]+states).Var()
        cp.Add(cp.AllowedAssignments([aggregate],[[s] for s in sorted(allowed)]))
    expired=[False]
    def stop():
        expired[0]=time.perf_counter()>=end
        return expired[0]
    guard(end);limit=cp.CustomLimit(stop)
    cp.NewSearch(cp.Phase(list(ys.values()),cp.CHOOSE_MIN_SIZE_LOWEST_MIN,cp.ASSIGN_MIN_VALUE),[limit])
    try:
        found=cp.NextSolution()
        mapping=[ys[r].Value() for r in range(len(q))] if found else None
        exhausted=not expired[0]
    finally:cp.EndSearch()
    guard(end)
    if found:return dict(mapping=mapping,state=rank_of(mapping,tables,base))
    if not exhausted:raise Deadline()
    return None

class FeasibilityLBBD(Projection):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,hall=False,**kwargs)
        self.active=set(self.frontier)
        self.stats['exposed_conflict_entities']=len(self.active)
    def oracle(self,i,interval,forbidden):
        answer=super().oracle(i,interval,forbidden)
        if not answer['sat']:answer['core']=frozenset(forbidden)
        return answer
    def learn_failure(self,i,interval,core):
        self.cuts.append(dict(component=i,interval=interval,core=frozenset(core),subset_minimal=False))
        self.stats['resource_cuts_learned']+=1;self.check_cut_limit()

def solve(method,identity,tables,base,budget):
    if method not in ('traditional_cp','lbbd'):return run(method,identity,tables,base,budget)
    start=time.perf_counter();end=start+budget;engine=None
    try:
        if method=='traditional_cp':result=consensus(lambda allowed:traditional_query(identity,tables,base,allowed,end))
        else:
            engine=FeasibilityLBBD(identity,tables,base,end)
            result=consensus(engine.query)
        guard(end)
    except (Deadline,ResourceLimit,RecursionError) as exc:
        result=dict(label='UNKNOWN',reason='budget' if isinstance(exc,Deadline) else 'resource_limit',certificate=False,mappings=[])
    except Unsupported as exc:
        result=dict(label='UNKNOWN',reason='unsupported',detail=str(exc),certificate=False,mappings=[])
    result.update(seconds=time.perf_counter()-start,route=method)
    if engine is not None:result.update(engine.stats)
    if result['seconds']>budget:result.update(label='UNKNOWN',reason='deadline_overrun',certificate=False)
    return result
