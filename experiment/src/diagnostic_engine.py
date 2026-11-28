"""Typed, proof-oriented diagnosis. Identity priors never consume observations."""
import time,copy
import numpy as np
from ortools.sat.python import cp_model
from complex_core import ComplexProblem
from inference import dfs_search,LABELS

S,V,U,NA=range(4)

def normalized_loads(obs,typing=True):
    if not obs.get('loads_complete',False):return None
    if not typing:return {int(k):np.array(v,float) for k,v in obs['loads'].items()}
    factor={'N':1.,'kN':1000.}.get(obs.get('force_unit'))
    rot=np.array(obs.get('force_frame_to_global',[]),float)
    if factor is None or rot.shape!=(3,3) or not np.allclose(rot.T@rot,np.eye(3),atol=1e-8) or not np.isclose(np.linalg.det(rot),1):return None
    if any(not np.all(np.isfinite(v)) for v in obs['loads'].values()):return None
    return {int(k):rot@np.array(v,float)*factor for k,v in obs['loads'].items()}

def existence(identity,task):
    if not task.get('existence_profile'):return None
    if not task['observation'].get('geometry_complete',False) or not identity.get('domain_complete'):return None
    expected=identity.get('registered_positions',{}).get('0')
    if expected is None:return None
    return bool(np.any(np.max(np.abs(np.array(identity['candidate_xyz'])-expected),axis=1)<identity['coordinate_tolerance']))

def early_check(identity,task,typing=True):
    obs=task['observation'];present=existence(identity,task)
    if task.get('optional_exists'):
        if present is False:return NA,'verified_optional_absence'
        if present is None:return U,'optional_guard_unresolved'
    if task.get('required_exists') and present is False:return V,'registered_required_interface_absent'
    if obs.get('material_complete') and abs(obs['elastic']-task['expected_elastic'])>.01*task['expected_elastic']:return V,'global_material_witness'
    loads=normalized_loads(obs,typing)
    if loads is not None:
        expected=np.array(task['expected_force_global_N'])
        if len(loads)!=1 or not any(np.allclose(f,expected,rtol=0,atol=.1) for f in loads.values()):return V,'global_force_witness'
    if not identity.get('domain_complete',False):return U,'identity_evidence_open'
    return None,None

def local_tables(identity,task,typing=True):
    N=len(identity['candidate_xyz']);obs=task['observation'];loads=normalized_loads(obs,typing);force=np.full(N,U if loads is None else V,np.int8)
    if loads is not None and len(loads)==1:
        for u,f in loads.items():
            if np.allclose(f,task['expected_force_global_N'],rtol=0,atol=.1):force[u]=S
    bc=np.full(N,U if not obs.get('bc_complete',False) else V,np.int8)
    if obs.get('bc_complete'):
        for u,dofs in obs['bcs'].items():
            if {'UX','UY','UZ'}<=set(dofs):bc[int(u)]=S
    material=(S if abs(obs['elastic']-task['expected_elastic'])<=.01*task['expected_elastic'] else V) if obs.get('material_complete') else U
    a=np.broadcast_to(force[:,None],(N,N));b=np.broadcast_to(bc[None,:],(N,N));joint=np.where((a==V)|(b==V)|(material==V),V,np.where((a==U)|(b==U)|(material==U),U,S)).astype(np.int8)
    return joint,a,b,material

def scoped_contradiction(identity,task,typing=True):
    """A relaxation certificate only proves violation, never satisfaction or target identity.

    Drop unrelated assembly relations, retain checked roles, independent CAD bindings and
    distinctness. If even this larger assignment space cannot meet the known physical
    obligations, no full identity can meet them. Inventory coverage is required.
    """
    from scipy.optimize import linear_sum_assignment
    obs=task['observation']
    if not obs.get('geometry_complete',False):return None
    N=len(identity['candidate_xyz']);roles=sorted({0,2}|{int(r) for r in identity['registered_positions']});domains=np.ones((len(roles),N),bool);xyz=np.array(identity['candidate_xyz']);loads=normalized_loads(obs,typing)
    for j,r in enumerate(roles):
        point=identity['registered_positions'].get(str(r))
        if point is not None:
            domains[j]&=np.max(np.abs(xyz-point),axis=1)<identity['coordinate_tolerance']
            if not domains[j].any():return None # unqualified binding is not an absence proof
        if r==0 and loads is not None:
            valid=np.zeros(N,bool)
            if len(loads)==1:
                for u,f in loads.items():valid[u]=np.allclose(f,task['expected_force_global_N'],rtol=0,atol=.1)
            domains[j]&=valid
        if r==2 and obs.get('bc_complete',False):domains[j]&=np.array([{'UX','UY','UZ'}<=set(obs['bcs'].get(str(u),[])) for u in range(N)])
    rows,cols=linear_sum_assignment((~domains).astype(np.int8));possible=len(rows)==len(roles) and bool(domains[rows,cols].all())
    if possible:return None
    return {'roles':roles,'candidate_sets':[np.flatnonzero(d).tolist() for d in domains],'proof':'no injective scope assignment even after dropping assembly relations'}

class GoalProblem(ComplexProblem):
    def __init__(self,identity,table=None,allowed=None,cycle=False):
        super().__init__(identity,cycle)
        if table is not None:
            mask=np.isin(table,allowed);r,s=0,2
            if np.all(mask) and (r,s) not in self.compat:return
            if (r,s) in self.compat:mask=mask&self.compat[r,s]
            else:self.neighbors[r].append(s);self.neighbors[s].append(r)
            self.compat[r,s]=mask;self.compat[s,r]=mask.T

def query_dfs(identity,table,allowed,unary=None,pairs=None,cycle=False,timeout=1,budget=1000000):
    start=time.perf_counter();p=GoalProblem(identity,table,allowed,cycle);remaining=timeout-(time.perf_counter()-start)
    if remaining<=0:return {'status':'UNKNOWN','mapping':None,'nodes':0,'seconds':time.perf_counter()-start}
    r=dfs_search(p,unary,pairs,'learned' if unary is not None else 'lcv',budget=budget,cache=1,timeout=remaining)
    status='SAT' if r['mappings'] else ('UNSAT' if r['complete'] else 'UNKNOWN')
    return {'status':status,'mapping':r['mappings'][0] if r['mappings'] else None,'nodes':r['nodes'],'seconds':time.perf_counter()-start}

def query_cp(identity,table,allowed,cycle=False,timeout=1):
    start=time.perf_counter();p=GoalProblem(identity,table,allowed,cycle);m=cp_model.CpModel();ys=[]
    for r in range(p.n):
        values=np.flatnonzero(p.domains[r]).tolist()
        if not values:return {'status':'UNSAT','mapping':None,'nodes':0,'seconds':time.perf_counter()-start}
        ys.append(m.new_int_var_from_domain(cp_model.Domain.from_values(values),f'y{r}'))
    m.add_all_different(ys)
    for (r,s),mat in p.compat.items():
        if r<s:m.add_allowed_assignments([ys[r],ys[s]],np.argwhere(mat).tolist())
    remaining=timeout-(time.perf_counter()-start)
    if remaining<=0:return {'status':'UNKNOWN','mapping':None,'nodes':0,'seconds':time.perf_counter()-start}
    solver=cp_model.CpSolver();solver.parameters.num_search_workers=1;solver.parameters.max_time_in_seconds=remaining;solver.parameters.random_seed=20261101;status=solver.solve(m)
    label='SAT' if status in (cp_model.OPTIMAL,cp_model.FEASIBLE) else ('UNSAT' if status==cp_model.INFEASIBLE else 'UNKNOWN')
    return {'status':label,'mapping':[solver.value(v) for v in ys] if label=='SAT' else None,'nodes':solver.num_branches,'seconds':time.perf_counter()-start}

def consensus(identity,table,backend='cp',unary=None,pairs=None,cycle=False,timeout=1,witness=None,node_budget=1000000):
    start=time.perf_counter();queries=[]
    def ask(allowed):
        remaining=timeout-(time.perf_counter()-start)
        if remaining<=0:return {'status':'UNKNOWN','mapping':None,'nodes':0,'seconds':0}
        result=(query_cp(identity,table,allowed,cycle,remaining) if backend=='cp' else query_dfs(identity,table,allowed,unary,pairs,cycle,remaining,node_budget));queries.append(result);return result
    first={'mapping':witness,'status':'SAT'} if witness is not None else ask([S,V,U,NA])
    if first['status']!='SAT':return {'label':'UNKNOWN','reason':'identity_inconsistent' if first['status']=='UNSAT' else 'budget','queries':queries,'mappings':[],'certificate':False}
    y=first['mapping'];value=int(table[y[0],y[2]]);maps=[y]
    if value==U:return {'label':'UNKNOWN','reason':'missing_evidence_witness','queries':queries,'mappings':maps,'certificate':True}
    other=ask([v for v in [S,V,U,NA] if v!=value])
    if other['status']=='UNSAT':label=LABELS[value];reason='counterexample_excluded';cert=True
    elif other['status']=='SAT':label='UNKNOWN';reason='conflicting_identity_witnesses';maps.append(other['mapping']);cert=True
    else:label='UNKNOWN';reason='budget';cert=False
    return {'label':label,'reason':reason,'queries':queries,'mappings':maps,'certificate':cert}

def enumerate_diagnosis(identity,table,unary=None,pairs=None,cycle=False,timeout=1,node_budget=1000000,top1=False):
    start=time.perf_counter();p=ComplexProblem(identity,cycle);domains=p.domains.copy();nodes=0;states=set();maps=[];stopped=False;truncated=False;found_any=False
    def rec(d):
        nonlocal nodes,stopped,truncated,found_any
        if stopped:return
        if nodes>=node_budget or time.perf_counter()-start>=timeout:stopped=True;truncated=True;return
        nodes+=1
        if not p.propagate(d):return
        sizes=d.sum(1)
        if np.all(sizes==1):
            found_any=True;y=np.argmax(d,axis=1).tolist();val=int(table[y[0],y[2]]);states.add(val)
            if len(maps)<5:maps.append(y)
            if top1 or len(states)>1 or U in states:stopped=True
            return
        r=int(np.argmin(np.where(sizes>1,sizes,p.N+1)));values=[]
        for u in np.flatnonzero(d[r]):
            score=float(unary[r,u]) if unary is not None else sum(np.log1p(np.count_nonzero(p.compat[r,s][u]&d[s])) for s in p.neighbors[r])
            if pairs:
                for s in p.neighbors[r]:
                    if sizes[s]==1 and (r,s) in pairs:score+=float(pairs[r,s][u,np.flatnonzero(d[s])[0]])
            values.append((-score,int(u)))
        for _,u in sorted(values):
            nxt=d.copy();nxt[r]=False;nxt[r,u]=True;rec(nxt)
            if stopped:return
    rec(domains)
    if truncated or not found_any:label='UNKNOWN';reason='budget' if truncated else 'identity_inconsistent';cert=False
    elif len(states)>1 or U in states:label='UNKNOWN';reason='conflict_or_missing';cert=True
    else:label=LABELS[next(iter(states))];reason='top1_unsafe' if top1 else 'enumeration_complete';cert=not top1
    return {'label':label,'reason':reason,'mappings':maps,'certificate':cert,'queries':[{'nodes':nodes,'status':'UNKNOWN' if truncated else 'DONE'}]}

def solve(identity,task,backend='cp',unary=None,pairs=None,cycle=False,early=True,typing=True,mode='query',timeout=1,node_budget=1000000,scope=False):
    start=time.perf_counter()
    if early:
        value,reason=early_check(identity,task,typing)
        if value is not None:return {'label':LABELS[value],'reason':reason,'mappings':[],'queries':[],'certificate':True,'nodes':0,'seconds':time.perf_counter()-start}
    elif not identity.get('domain_complete',False):return {'label':'UNKNOWN','reason':'identity_evidence_open','mappings':[],'queries':[],'certificate':False,'nodes':0,'seconds':time.perf_counter()-start}
    if scope:
        proof=scoped_contradiction(identity,task,typing)
        if proof is not None:return {'label':'VIOLATES','reason':'scope_relaxation_contradiction','scope_proof':proof,'mappings':[],'queries':[],'certificate':True,'nodes':0,'seconds':time.perf_counter()-start}
    joint,force,bc,material=local_tables(identity,task,typing)
    remaining=max(0.,timeout-(time.perf_counter()-start))
    if mode in ('enumerate','top1'):result=enumerate_diagnosis(identity,joint,unary,pairs,cycle,remaining,node_budget,mode=='top1')
    elif mode=='independent_predicates':
        one=consensus(identity,force,backend,unary,pairs,cycle,remaining,node_budget=node_budget);remaining=max(0.,timeout-(time.perf_counter()-start));two=consensus(identity,bc,backend,unary,pairs,cycle,remaining,node_budget=node_budget);labels=[one['label'],two['label'],LABELS[material]];label='VIOLATES' if 'VIOLATES' in labels else ('UNKNOWN' if 'UNKNOWN' in labels else 'SATISFIES');result={'label':label,'reason':'separate_predicate_aggregation','certificate':one['certificate'] and two['certificate'],'mappings':one['mappings']+two['mappings'],'queries':one['queries']+two['queries']}
    else:result=consensus(identity,joint,backend,unary,pairs,cycle,remaining,node_budget=node_budget)
    result['nodes']=sum(q['nodes'] for q in result['queries']);result['seconds']=time.perf_counter()-start;return result
