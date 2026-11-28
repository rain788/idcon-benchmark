"""Inference-only code. This module never opens protected reference data."""
import time
import numpy as np
from ortools.sat.python import cp_model

LABELS=['SATISFIES','VIOLATES','UNKNOWN','NOT_APPLICABLE']

class Problem:
    def __init__(self,identity):
        self.identity=identity;self.xyz=np.asarray(identity['candidate_xyz']);self.n=identity['role_count'];self.N=len(self.xyz)
        self.adj=np.zeros((self.N,self.N),bool)
        for a,b in identity['candidate_edges']:self.adj[a,b]=self.adj[b,a]=True
        self.lengths=np.linalg.norm(self.xyz[:,None,:]-self.xyz[None,:,:],axis=-1)
        self.compat={};self.neighbors=[[] for _ in range(self.n)]
        for r,s,length,implicit in identity['role_edges']:
            mat=self.adj & (np.abs(self.lengths-length)<identity['length_tolerance'])
            self.compat[r,s]=mat;self.compat[s,r]=mat.T;self.neighbors[r].append(s);self.neighbors[s].append(r)
        self.domains=np.ones((self.n,self.N),bool)
        for r in range(self.n):self.domains[r]&=self.adj.sum(axis=1)>=len(self.neighbors[r])
        for r,pos in identity['registered_positions'].items():self.domains[int(r)]&=np.max(np.abs(self.xyz-np.array(pos)),axis=1)<identity['coordinate_tolerance']
        self.propagation_checks=0

    def propagate(self,domains):
        changed=True
        while changed:
            changed=False
            if np.any(domains.sum(axis=1)==0):return False
            singles={};
            for r in range(self.n):
                if domains[r].sum()==1:
                    u=int(np.flatnonzero(domains[r])[0])
                    if u in singles:return False
                    singles[u]=r
            for u,r in singles.items():
                for s in range(self.n):
                    if s!=r and domains[s,u]:domains[s,u]=False;changed=True
            for (r,s),compat in self.compat.items():
                self.propagation_checks+=1
                support=np.any(compat[:,domains[s]],axis=1)
                remove=domains[r]&~support
                if remove.any():domains[r,remove]=False;changed=True
        return not np.any(domains.sum(axis=1)==0)

def verify_local(obs,target,support,kind):
    """Four-status verifier; distinct implementation from the reference labeler."""
    if obs.get('applicable') is False:return 'NOT_APPLICABLE'
    if not obs.get('domain_complete',False):return 'UNKNOWN'
    if kind=='response':
        value=obs.get('response');threshold=obs['response_limit']
        if value is None:return 'UNKNOWN'
        return 'SATISFIES' if value<=threshold else 'VIOLATES'
    outcomes=[]
    if obs.get('loads_available'):
        forces=np.array(list(obs['loads'].values()),dtype=float)
        vector=np.array(obs['loads'].get(str(target),[0,0,0]),dtype=float)
        good=forces.shape==(1,3) and np.all(np.abs(vector-np.array([0.,-10.,0.]))<=np.array([1e-6,.1,1e-6]))
        outcomes.append(0 if good else 1)
    else:outcomes.append(2)
    fixed=obs['bcs'].get(str(support),[])
    outcomes.append(0 if all(x in fixed for x in ('UX','UY','UZ')) else 1)
    outcomes.append(0 if np.isclose(obs['elastic'],210000,rtol=.01,atol=0) else 1)
    return LABELS[1 if 1 in outcomes else (2 if 2 in outcomes else 0)]

def status_table(problem,task):
    obs=task['observation'];N=problem.N
    if not obs['applicable']:return np.full((N,N),3,dtype=np.int8)
    if not obs.get('domain_complete',False):return np.full((N,N),2,dtype=np.int8)
    if task['kind']=='response':
        val=2 if obs['response'] is None else (0 if obs['response']<=obs['response_limit'] else 1)
        return np.full((N,N),val,dtype=np.int8)
    load=np.full(N,2 if not obs['loads_available'] else 1,dtype=np.int8)
    if obs['loads_available'] and len(obs['loads'])==1:
        key,vector=next(iter(obs['loads'].items()))
        if np.all(np.abs(np.array(vector)-[0.,-10.,0.])<=[1e-6,.1,1e-6]):load[int(key)]=0
    bc=np.array([all(x in obs['bcs'].get(str(v),[]) for x in ('UX','UY','UZ')) for v in range(N)])
    violation=(load[:,None]==1)|(~bc[None,:])|not_material(obs['elastic'])
    return np.where(violation,1,np.broadcast_to(load[:,None],(N,N))).astype(np.int8)

def not_material(value):return abs(value-210000)>2100

def dfs_search(problem,scores=None,pairs=None,mode='lcv',budget=10000,timeout=5,task=None,cache=5,all_solutions=False):
    start=time.perf_counter();nodes=0;found=[];values=set();timed=False;exceeded=False;stop=False;certificate=False
    domains=problem.domains.copy();problem.propagation_checks=0
    root_ok=problem.propagate(domains)
    table=status_table(problem,task) if task else None
    constant=None
    if table is not None and root_ok:
        vals=np.unique(table[np.ix_(domains[0],domains[1])])
        if len(vals)==1:constant=int(vals[0])
    def visit(dom):
        nonlocal nodes,timed,exceeded,stop,certificate
        if stop:return
        if nodes>=budget:exceeded=True;stop=True;return
        if time.perf_counter()-start>=timeout:timed=True;stop=True;return
        nodes+=1
        if not problem.propagate(dom):return
        sizes=dom.sum(axis=1)
        if np.all(sizes==1):
            y=np.argmax(dom,axis=1).tolist()
            if len(found)<cache or all_solutions:found.append(y)
            if task:
                val=int(table[y[0],y[1]]);values.add(val)
                if constant is not None:certificate=True;stop=True
                elif val==2 or len(values)>1:certificate=True;stop=True
            elif not all_solutions and len(found)>=cache:stop=True
            return
        r=int(np.argmin(np.where(sizes>1,sizes,problem.N+1)))
        candidates=np.flatnonzero(dom[r]);ranking=[]
        for u in candidates:
            if mode=='lcv':
                score=sum(np.log1p(np.count_nonzero(problem.compat[r,s][u]&dom[s])) for s in problem.neighbors[r])
            elif mode=='fixed':score=-float(u)
            else:
                score=float(scores[r,u])
                if pairs:
                    for s in problem.neighbors[r]:
                        if sizes[s]==1 and (r,s) in pairs:score+=float(pairs[r,s][u,np.flatnonzero(dom[s])[0]])
            ranking.append((-score,int(u)))
        for _,u in sorted(ranking):
            nxt=dom.copy();nxt[r]=False;nxt[r,u]=True;visit(nxt)
            if stop:return
    if root_ok:visit(domains)
    complete=not timed and not exceeded and not stop
    # A singleton set of outcomes requires complete search, or a sound full-domain table certificate.
    if task:
        if not found:label='UNKNOWN';reason='identity_inconsistent' if complete or not root_ok else 'truncated'
        elif constant is not None:label=LABELS[constant];reason='domain_table_and_existence'
        elif len(values)>1 or 2 in values:label='UNKNOWN';reason='ambiguity_or_missing_observation'
        elif complete:label=LABELS[next(iter(values))];reason='exhaustive'
        else:label='UNKNOWN';reason='truncated'
    else:label=None;reason='matching'
    return {'label':label,'reason':reason,'mappings':found,'nodes':nodes,'propagation_checks':problem.propagation_checks,'complete':complete,'seconds':time.perf_counter()-start,'timeout':timed,'budget_exhausted':exceeded,'certificate':certificate or complete}

def cp_search(problem,task=None,timeout=5,enumerate_maps=False,limit=20000):
    start=time.perf_counter();branch_count=0;seen=[];query_statuses=[];values=[];allcomplete=True
    tab=status_table(problem,task) if task else None
    def make_model(label=None):
        model=cp_model.CpModel();ys=[]
        for r in range(problem.n):
            vals=np.flatnonzero(problem.domains[r]).tolist()
            if not vals:return None,None
            ys.append(model.new_int_var_from_domain(cp_model.Domain.from_values(vals),f'y{r}'))
        model.add_all_different(ys)
        for (r,s),mat in problem.compat.items():
            if r<s:model.add_allowed_assignments([ys[r],ys[s]],np.argwhere(mat).tolist())
        if label is not None:
            allowed=np.argwhere(tab==label).tolist()
            if not allowed:return None,None
            model.add_allowed_assignments([ys[0],ys[1]],allowed)
        return model,ys
    if enumerate_maps:
        model,ys=make_model()
        if model is None:return {'mappings':[],'complete':True,'seconds':time.perf_counter()-start}
        class Collector(cp_model.CpSolverSolutionCallback):
            def on_solution_callback(self):
                seen.append([self.value(v) for v in ys])
                if len(seen)>=limit:self.stop_search()
        solver=cp_model.CpSolver();solver.parameters.num_search_workers=1;solver.parameters.max_time_in_seconds=timeout;solver.parameters.enumerate_all_solutions=True
        status=solver.solve(model,Collector());return {'mappings':seen,'complete':status in (cp_model.OPTIMAL,cp_model.INFEASIBLE) and len(seen)<limit,'seconds':time.perf_counter()-start}
    for label in (range(4) if task else [None]):
        model,ys=make_model(label)
        if model is None:query_statuses.append('INFEASIBLE_BY_EMPTY_TABLE');continue
        solver=cp_model.CpSolver();solver.parameters.num_search_workers=1;solver.parameters.max_time_in_seconds=max(.001,timeout-(time.perf_counter()-start));solver.parameters.random_seed=20261027
        status=solver.solve(model);branch_count+=solver.num_branches;query_statuses.append(solver.status_name(status))
        if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
            seen.append([solver.value(v) for v in ys]);values.append(label)
        elif status!=cp_model.INFEASIBLE:allcomplete=False
        if len(values)>1:break
    result=LABELS[values[0]] if task and len(values)==1 and allcomplete else 'UNKNOWN'
    return {'label':result,'reason':'cp_status_queries','mappings':seen,'nodes':branch_count,'complete':allcomplete,'seconds':time.perf_counter()-start,'query_statuses':query_statuses,'certificate':allcomplete}
