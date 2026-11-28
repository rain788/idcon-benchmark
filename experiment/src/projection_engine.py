"""Exact single-port separator projection; sparse monolithic CP is the fallback/control.

No protected references are imported. Class merging always verifies colored isomorphism.
"""
import itertools,time
from collections import deque
import networkx as nx
import numpy as np
from ortools.sat.python import cp_model
from scipy.optimize import linear_sum_assignment
from diagnostic_engine import early_check,normalized_loads,scoped_contradiction

LABELS=['SATISFIES','VIOLATES','UNKNOWN','NOT_APPLICABLE'];S,V,U=0,1,2
class Deadline(Exception):pass
class Unsupported(Exception):pass
def guard(end):
    if time.perf_counter()>=end:raise Deadline()
def combine(values):return V if V in values else (U if U in values else S)

def vectors(identity,task):
    N=len(identity['candidate_xyz']);obs=task['observation'];loads=normalized_loads(obs);f=np.full(N,U if loads is None else V,dtype=np.int8);b=np.full(N,U if not obs.get('bc_complete') else V,dtype=np.int8)
    if loads is not None and len(loads)==1:
        for u,v in loads.items():
            if np.allclose(v,task['expected_force_global_N'],atol=.1,rtol=0):f[u]=S
    if obs.get('bc_complete'):
        for u,d in obs['bcs'].items():
            if {'UX','UY','UZ'}<=set(d):b[int(u)]=S
    material=U if not obs.get('material_complete') else (S if abs(obs['elastic']-task['expected_elastic'])<=.01*task['expected_elastic'] else V)
    return f,b,material

def graph_data(identity):
    g=nx.Graph();g.add_nodes_from(range(len(identity['candidate_xyz'])));g.add_edges_from(identity['candidate_edges']);q=nx.Graph();q.add_nodes_from(range(identity['role_count']));q.add_edges_from((r,s) for r,s,_,_ in identity['role_edges']);xyz=np.asarray(identity['candidate_xyz']);anchors={}
    for r,point in identity['registered_positions'].items():
        found=np.flatnonzero(np.max(np.abs(xyz-point),axis=1)<identity['coordinate_tolerance'])
        if len(found)!=1:raise Unsupported('nonunique or missing anchor')
        anchors[int(r)]=int(found[0])
    if len(set(anchors.values()))!=len(anchors):raise Unsupported('colliding anchors')
    return g,q,anchors

def sparse_query(identity,end,force,bc,material,allowed=None,roles=None,nodes=None,states=None,prepared=None,cycle_domains=None):
    """Sparse AC + native AllDifferent + edge tables; no dense NxN compatibility matrices."""
    try:
        guard(end);g,q,anchors=prepared or graph_data(identity);roles=set(q) if roles is None else set(roles);nodes=set(g) if nodes is None else set(nodes);anchors={r:u for r,u in anchors.items() if r in roles};used=set(anchors.values());d={r:({anchors[r]} if r in anchors else {u for u in nodes-used if g.degree[u]>=q.degree[r]}) for r in roles};states=states or {}
        if cycle_domains:
            for r in d:d[r]&=cycle_domains[r]
        for r,value in states.items():d[r]={u for u in d[r] if int((force if r==0 else bc)[u])==value}
        edges=[(r,s,l) for r,s,l,_ in identity['role_edges'] if r in roles and s in roles];xyz=np.asarray(identity['candidate_xyz']);adj={u:set(g[u]) for u in nodes};lengths={(r,s):l for r,s,l in edges};lengths.update({(s,r):l for r,s,l in edges});neighbors={r:set(q[r])&roles for r in roles}
        def compatible(r,u,s,v):
            length=lengths[r,s]
            return v in adj[u] and (length is None or abs(np.linalg.norm(xyz[u]-xyz[v])-length)<identity['length_tolerance'])
        queue=deque((r,s) for r in roles for s in neighbors[r])
        while queue:
            guard(end);r,s=queue.popleft();new={u for u in d[r] if any(compatible(r,u,s,v) for v in adj[u]&d[s])}
            if not new:return {'status':'UNSAT','mapping':None,'nodes':0}
            if new!=d[r]:d[r]=new;queue.extend((v,r) for v in neighbors[r] if v!=s)
        m=cp_model.CpModel();ys={}
        for r in sorted(roles):
            if not d[r]:return {'status':'UNSAT','mapping':None,'nodes':0}
            ys[r]=m.new_int_var_from_domain(cp_model.Domain.from_values(sorted(d[r])),f'y{r}')
        m.add_all_different(list(ys.values()))
        for r,s,length in edges:
            guard(end);pairs=[(u,v) for u in sorted(d[r]) for v in sorted(adj[u]&d[s]) if compatible(r,u,s,v)]
            if not pairs:return {'status':'UNSAT','mapping':None,'nodes':0}
            m.add_allowed_assignments([ys[r],ys[s]],pairs)
        if allowed is not None:
            a=m.new_int_var(0,2,'force');b=m.new_int_var(0,2,'bc');m.add_element(ys[0],force.tolist(),a);m.add_element(ys[2],bc.tolist(),b);m.add_allowed_assignments([a,b],[(f,c) for f in range(3) for c in range(3) if combine([f,c,material]) in allowed])
        guard(end);solver=cp_model.CpSolver();solver.parameters.num_search_workers=1;solver.parameters.max_time_in_seconds=end-time.perf_counter();solver.parameters.random_seed=20261102;status=solver.solve(m)
        return {'status':'SAT' if status in (cp_model.OPTIMAL,cp_model.FEASIBLE) else ('UNSAT' if status==cp_model.INFEASIBLE else 'UNKNOWN'),'mapping':{r:solver.value(y) for r,y in ys.items()} if status in (cp_model.OPTIMAL,cp_model.FEASIBLE) else None,'nodes':solver.num_branches}
    except Deadline:return {'status':'UNKNOWN','mapping':None,'nodes':0}

def cactus_lengths(g):
    values={u:[] for u in g}
    for block in nx.biconnected_components(g):
        if len(block)<3:continue
        sub=g.subgraph(block)
        if sub.number_of_edges()!=len(block) or any(d!=2 for _,d in sub.degree):return None
        for u in block:values[u].append(len(block))
    return values

def sparse_diagnosis(identity,task,end,prepared=None,cycle=False):
    f,b,material=vectors(identity,task);cycle_domains=None
    if cycle:
        from collections import Counter
        prepared=prepared or graph_data(identity);g,q,_=prepared;hc=cactus_lengths(g);qc=cactus_lengths(q)
        if hc is not None and qc is not None:
            # Compute once per signature, not once per role-node pair: a strong baseline
            # must not pay avoidable Python Counter construction hundreds of thousands of times.
            host_signatures={}
            for u,values in hc.items():host_signatures.setdefault(tuple(sorted(values)),set()).add(u)
            required={}
            for values in {tuple(sorted(v)) for v in qc.values()}:
                required[values]=set().union(*(nodes for signature,nodes in host_signatures.items() if not (Counter(values)-Counter(signature))))
            cycle_domains={r:required[tuple(sorted(qc[r]))] for r in q}
    first=sparse_query(identity,end,f,b,material,prepared=prepared,cycle_domains=cycle_domains)
    if first['status']!='SAT':return {'label':'UNKNOWN','reason':'identity_inconsistent' if first['status']=='UNSAT' else 'budget','certificate':first['status']=='UNSAT','mappings':[],'nodes':first['nodes']}
    y=first['mapping'];v=combine([int(f[y[0]]),int(b[y[2]]),material]);maps=[[y[r] for r in range(identity['role_count'])]]
    if v==U:return {'label':'UNKNOWN','reason':'missing_evidence_witness','certificate':True,'mappings':maps,'nodes':first['nodes']}
    second=sparse_query(identity,end,f,b,material,allowed=[x for x in range(3) if x!=v],prepared=prepared,cycle_domains=cycle_domains)
    if second['status']=='SAT':maps.append([second['mapping'][r] for r in range(identity['role_count'])])
    return {'label':LABELS[v] if second['status']=='UNSAT' else 'UNKNOWN','reason':'counterexample_excluded' if second['status']=='UNSAT' else ('conflicting_identity_witnesses' if second['status']=='SAT' else 'budget'),'certificate':second['status']!='UNKNOWN','mappings':maps,'nodes':first['nodes']+second['nodes']}

def partition(g,q,anchors,end,maximum=32):
    guard(end)
    for r,s in q.edges:
        if r in anchors and s in anchors and not g.has_edge(anchors[r],anchors[s]):raise Unsupported('anchor relation mismatch')
    qs=[set(c) for c in nx.connected_components(q.subgraph(set(q)-set(anchors)))];hs=[set(c) for c in nx.connected_components(g.subgraph(set(g)-set(anchors.values())))];valid=[]
    for h in hs:
        ports={u for u in h if set(g[u])&set(anchors.values())}
        if not ports:continue
        if len(ports)!=1 or len(h)>maximum:raise Unsupported('host multiport or component exceeds fixed limit')
        valid.append(h)
    if not qs or any(len({r for r in c if set(q[r])&set(anchors)})!=1 for c in qs):raise Unsupported('query not single-port')
    return qs,valid

def path_cycle_orders(graph,root):
    """Recognize a single rooted path ending in a simple cycle; return its two orientations."""
    cycles=nx.cycle_basis(graph)
    if len(cycles)!=1:return None
    cyc=set(cycles[0]);entry=min(cyc,key=lambda u:nx.shortest_path_length(graph,root,u));path=nx.shortest_path(graph,root,entry)
    if set(path)|cyc!=set(graph) or len(graph.edges)!=len(graph):return None
    if any(d!=2 for u,d in graph.subgraph(cyc).degree):return None
    orders=[]
    for neighbor in sorted(set(graph[entry])&cyc):
        ring=[entry,neighbor]
        while len(ring)<len(cyc):ring.append(next(u for u in graph[ring[-1]] if u in cyc and u!=ring[-2]))
        order=path[:-1]+ring
        if len(order)!=len(set(order)):return None
        orders.append(order)
    return (len(path)-1,len(cyc)),orders

def classes(components,graph,color,end,share=True):
    groups=[];items=[];buckets={}
    for component in components:
        guard(end);cg=graph.subgraph(component).copy();nx.set_node_attributes(cg,{u:repr(color(u)) for u in cg},'color');root=next((u for u in cg if color(u)[0]),None);form=path_cycle_orders(cg,root) if root is not None else None
        if form:
            shape,orders=form;order=min(orders,key=lambda order:tuple(cg.nodes[u]['color'] for u in order));key=('rooted_cycle',shape,tuple(cg.nodes[u]['color'] for u in order));idx=buckets.get(key,[None])[0] if share else None
            if idx is None:idx=len(groups);groups.append({'graph':cg,'nodes':component,'order':order,'form':form});buckets.setdefault(key,[]).append(idx)
            items.append({'class':idx,'map':dict(zip(groups[idx]['order'],order)),'nodes':component});continue
        key=nx.weisfeiler_lehman_graph_hash(cg,node_attr='color');found=None
        if share:
            for idx in buckets.get(key,[]):
                matcher=nx.algorithms.isomorphism.GraphMatcher(groups[idx]['graph'],cg,node_match=lambda a,b:a['color']==b['color'])
                if matcher.is_isomorphic():found=(idx,dict(matcher.mapping));break
        if found is None:
            idx=len(groups);groups.append({'graph':cg,'nodes':component,'form':None});buckets.setdefault(key,[]).append(idx);found=(idx,{u:u for u in cg})
        items.append({'class':found[0],'map':found[1],'nodes':component})
    return groups,items

def assignment(mask):
    if mask.shape[1]<mask.shape[0]:return None
    rows,cols=linear_sum_assignment((~mask).astype(np.int8))
    return dict(zip(rows.tolist(),cols.tolist())) if len(rows)==mask.shape[0] and bool(mask[rows,cols].all()) else None

def projected(identity,task,end,share=True):
    if any(l is not None for _,_,l,_ in identity['role_edges']):raise Unsupported('metric constraints use general solver')
    g,q,anchors=graph_data(identity);qs,hs=partition(g,q,anchors,end);f,b,material=vectors(identity,task);ar=set(anchors);au=set(anchors.values())
    qc,qi=classes(qs,q,lambda r:(tuple(sorted(set(q[r])&ar)),0 if r==0 else (2 if r==2 else -1)),end,share)
    hc,hi=classes(hs,g,lambda u:(tuple(sorted(r for r,v in anchors.items() if g.has_edge(u,v))),int(f[u]),int(b[u])),end,share)
    outcomes={};local_calls=0
    for a,c in enumerate(qc):
        checked=sorted(set(c['nodes'])&{0,2})
        for z,h in enumerate(hc):
            guard(end);statesets=[sorted(set(int((f if r==0 else b)[u]) for u in h['nodes'])) for r in checked];answers={}
            for state in itertools.product(*statesets):
                guard(end);local_calls+=1
                if c.get('form') and h.get('form'):
                    answer={'status':'UNSAT','mapping':None,'nodes':0}
                    if c['form'][0]==h['form'][0]:
                        source=c['form'][1][0]
                        for order in h['form'][1]:
                            mapping={**anchors,**dict(zip(source,order))}
                            if all(all(g.has_edge(mapping[r],anchors[a]) for a in set(q[r])&ar) for r in source) and all(int((f if r==0 else b)[mapping[r]])==v for r,v in zip(checked,state)):
                                answer={'status':'SAT','mapping':mapping,'nodes':0};break
                else:answer=sparse_query(identity,end,f,b,material,roles=c['nodes']|ar,nodes=h['nodes']|au,states=dict(zip(checked,state)),prepared=(g,q,anchors))
                answers[state]=answer
            outcomes[a,z]=(checked,answers)
    possible={};unresolved=False;macros=[]
    values0=[int(f[anchors[0]])] if 0 in anchors else sorted(set(int(x) for x in f));values2=[int(b[anchors[2]])] if 2 in anchors else sorted(set(int(x) for x in b))
    for state in itertools.product(values0,values2):
        guard(end);wanted={0:state[0],2:state[1]};lo=np.zeros((len(qi),len(hi)),bool);up=lo.copy();lookups={}
        for i,a in enumerate(qi):
            for j,h in enumerate(hi):
                checked,answers=outcomes[a['class'],h['class']];key=tuple(wanted[r] for r in checked);answer=answers.get(key,{'status':'UNSAT'});lo[i,j]=answer['status']=='SAT';up[i,j]=answer['status']!='UNSAT';lookups[i,j]=answer
        matched=assignment(lo);upper=assignment(up);v=combine([*state,material]);macros.append({'states':list(state),'lower_edges':int(lo.sum()),'upper_edges':int(up.sum()),'matching':matched})
        if matched is not None:
            mapping=dict(anchors)
            for i,j in matched.items():
                local=lookups[i,j]['mapping'];a=qi[i];h=hi[j]
                for r,u in local.items():
                    if r not in ar:mapping[a['map'][r]]=h['map'][u]
            possible.setdefault(v,[mapping[r] for r in range(identity['role_count'])])
        elif upper is not None:unresolved=True
    if len(possible)>1:label='UNKNOWN';reason='conflicting_identity_witnesses';cert=True
    elif U in possible:label='UNKNOWN';reason='missing_evidence_witness';cert=True
    elif unresolved:label='UNKNOWN';reason='budget';cert=False
    elif not possible:label='UNKNOWN';reason='identity_inconsistent';cert=True
    else:label=LABELS[next(iter(possible))];reason='exact_separator_projection';cert=True
    return {'label':label,'reason':reason,'certificate':cert,'mappings':list(possible.values())[:2],'nodes':0,'local_queries':local_calls,'query_components':len(qi),'host_components':len(hi),'query_classes':len(qc),'host_classes':len(hc),'macro_states':macros,'route':'projection'}

def diagnose(identity,task,backend='project',timeout=.2,share=True,scope=True):
    start=time.perf_counter();end=start+timeout
    try:
        value,reason=early_check(identity,task)
        if value is not None:result={'label':LABELS[value],'reason':reason,'certificate':True,'mappings':[],'route':'independent'}
        elif scope and scoped_contradiction(identity,task) is not None:result={'label':'VIOLATES','reason':'scope_relaxation_contradiction','certificate':True,'mappings':[],'route':'relaxation'}
        elif backend in ('sparse_cp','sparse_cp_cycle'):result={**sparse_diagnosis(identity,task,end,cycle=backend=='sparse_cp_cycle'),'route':backend}
        else:
            try:result=projected(identity,task,end,share)
            except Unsupported as exc:result={**sparse_diagnosis(identity,task,end),'route':'fallback','fallback_reason':str(exc)}
    except Deadline:result={'label':'UNKNOWN','reason':'budget','certificate':False,'mappings':[],'route':'projection'}
    except Unsupported as exc:result={'label':'UNKNOWN','reason':'identity_binding_unsupported','certificate':False,'mappings':[],'route':'fallback','fallback_reason':str(exc)}
    elapsed=time.perf_counter()-start;result.update(seconds=elapsed,raw_label=result['label'])
    if elapsed>timeout:result.update(label='UNKNOWN',reason='deadline_overrun',certificate=False)
    return result
