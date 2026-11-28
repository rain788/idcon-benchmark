"""Equal-semantics controls for the frozen semantic diagnosis core.

No protected references or construction maps are imported by these solvers.
All exclusion is trusted CP / exhaustive search, not formal proof certification.
"""
import time
from collections import defaultdict
import networkx as nx
import numpy as np
from ortools.sat.python import cp_model
from semantic_projection import Projection, ResourceLimit, S, U, V, diagnose_tables
from projection_engine import Deadline, guard, graph_data

METHODS = ['semantic', 'whole_cp', 'plain_decomposition', 'materialized', 'vf2',
           'no_hall', 'no_query_reuse', 'eager_resources']


def rank_of(mapping, tables, base):
    return max([base]+[values[mapping[r]] for r, values in tables.items()])


def whole_query(identity, tables, base, allowed, end, seed=73019):
    """Direct global sparse CP, independent of decomposition and goal translation."""
    guard(end)
    g, q, anchors = graph_data(identity)
    xyz = np.asarray(identity['candidate_xyz'])
    model = cp_model.CpModel()
    domains = {r: ({anchors[r]} if r in anchors else
                   {u for u in g if u not in anchors.values() and g.degree[u] >= q.degree[r]}) for r in q}
    for _r, _v in {int(_r):set(_v) for _r,_v in identity.get('role_domains',{}).items()}.items():
        domains[_r] &= _v
    if any(not d for d in domains.values()):
        return None
    ys = {r: model.new_int_var_from_domain(cp_model.Domain.from_values(sorted(domains[r])), str(r)) for r in q}
    model.add_all_different(list(ys.values()))
    for r, s, length, _ in identity['role_edges']:
        guard(end)
        pairs = [(u, v) for u in domains[r] for v in g[u] if v in domains[s] and
                 (length is None or abs(np.linalg.norm(xyz[u]-xyz[v])-length) < identity['length_tolerance'])]
        if not pairs:
            return None
        model.add_allowed_assignments([ys[r], ys[s]], pairs)
    if set(allowed) != {S, U, V}:
        states = []
        for r, values in tables.items():
            p = model.new_int_var(S, V, 'p'+str(r))
            model.add_element(ys[r], values, p)
            states.append(p)
        aggregate = model.new_int_var(S, V, 'state')
        model.add_max_equality(aggregate, [base]+states)
        model.add_allowed_assignments([aggregate], [[s] for s in sorted(allowed)])
    guard(end)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = seed
    solver.parameters.max_time_in_seconds = max(1e-8, end-time.perf_counter())
    status = solver.solve(model)
    guard(end)
    if status == cp_model.INFEASIBLE:
        return None
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise Deadline()
    mapping = [solver.value(ys[r]) for r in range(len(q))]
    return {'mapping': mapping, 'state': rank_of(mapping, tables, base)}


def consensus(query):
    first = query({S,U,V})
    if first is None:
        return dict(label='UNKNOWN', reason='identity_inconsistent', certificate=True, mappings=[])
    mappings = [first['mapping']]
    if first['state'] == U:
        return dict(label='UNKNOWN', reason='missing_evidence_witness', certificate=True, mappings=mappings)
    other = query({S,U,V}-{first['state']})
    if other is not None:
        mappings.append(other['mapping'])
        return dict(label='UNKNOWN', reason='conflicting_identity_witnesses', certificate=True, mappings=mappings)
    return dict(label=['SATISFIES','UNKNOWN','VIOLATES'][first['state']],
                reason='counterexample_excluded', certificate=True, mappings=mappings)


class Variant(Projection):
    def __init__(self, *args, eager=False, reuse=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.reuse = reuse
        if eager:
            self.active = set(self.frontier)
            self.stats['exposed_conflict_entities'] = len(self.active)

    def query(self, allowed):
        if not self.reuse:
            self.cuts, self.hall_cuts, self.models = [], [], {}
            self.witnesses = defaultdict(list)
        return super().query(allowed)


class Materialized:
    """Complete local footprints + states, followed by exact disjoint combination.

    Includes all candidate nodes (no host-component cap), arbitrary unary roles,
    and a 20,000 configuration / 200,000 enumeration-node resource policy.
    """
    def __init__(self, identity, tables, base, end):
        self.identity, self.tables, self.base, self.end = identity, tables, base, end
        g, q, self.anchors = graph_data(identity)
        self.q = q
        xyz = np.asarray(identity['candidate_xyz'])
        lengths = {(r,s):l for r,s,l,_ in identity['role_edges']}
        lengths.update({(s,r):l for (r,s),l in list(lengths.items())})
        def legal(r,u,s,v):
            l=lengths[r,s]
            return g.has_edge(u,v) and (l is None or abs(np.linalg.norm(xyz[u]-xyz[v])-l)<identity['length_tolerance'])
        self.valid = all(legal(r,self.anchors[r],s,self.anchors[s]) for r,s in q.edges if r in self.anchors and s in self.anchors)
        self.configs=[]
        self.nodes=0
        if not self.valid:
            return
        for roles in nx.connected_components(q.subgraph(set(q)-set(self.anchors))):
            domains={r:{u for u in g if u not in self.anchors.values() and g.degree[u]>=q.degree[r]
                     and all(legal(r,u,a,self.anchors[a]) for a in set(q[r])&set(self.anchors))} for r in roles}
            seen={}
            def visit(mapping,used):
                guard(end)
                self.nodes+=1
                if self.nodes>200000:
                    raise MemoryError('materialization node policy')
                if len(mapping)==len(roles):
                    state=max([S]+[tables[r][u] for r,u in mapping.items() if r in tables])
                    seen.setdefault((frozenset(used),state),dict(mapping))
                    if sum(map(len,self.configs))+len(seen)>20000:
                        raise MemoryError('materialization configuration policy')
                    return
                candidates={r:{u for u in domains[r]-used if all(legal(r,u,s,mapping[s]) for s in set(q[r])&set(mapping))}
                            for r in roles-set(mapping)}
                r=min(candidates,key=lambda r:(len(candidates[r]),r))
                for u in sorted(candidates[r]):
                    visit({**mapping,r:u},used|{u})
            visit({},set())
            self.configs.append([(key[0],key[1],mapping) for key,mapping in seen.items()])
        self.configs.sort(key=len)

    def query(self, allowed):
        if not self.valid:
            return None
        base=max([self.base]+[self.tables[r][u] for r,u in self.anchors.items() if r in self.tables])
        def visit(k,used,mapping,state):
            guard(self.end)
            if k==len(self.configs):
                return {'mapping':[mapping[r] for r in range(len(self.q))], 'state':state} if state in allowed else None
            for footprint,rank,local in self.configs[k]:
                if not used&footprint:
                    answer=visit(k+1,used|footprint,{**mapping,**local},max(state,rank))
                    if answer is not None:
                        return answer
            return None
        return visit(0,set(),dict(self.anchors),base)


class VF2:
    """NetworkX non-induced monomorphism iterator, with exact metric checks."""
    def __init__(self, identity, tables, base, end):
        self.identity,self.tables,self.base,self.end=identity,tables,base,end
        self.g,self.q,self.anchors=graph_data(identity)

    def query(self, allowed):
        end=self.end;anchors=self.anchors;tables=self.tables;base=self.base
        class Matcher(nx.algorithms.isomorphism.GraphMatcher):
            def semantic_feasibility(m,u,r):
                guard(end)
                if r in anchors and anchors[r]!=u:
                    return False
                if u in anchors.values() and anchors.get(r)!=u:
                    return False
                if max(allowed)<V and r in tables and tables[r][u]>max(allowed):
                    return False
                return super().semantic_feasibility(u,r)
        from occupancy_validate import mapping_legal
        matcher=Matcher(self.g,self.q)
        for inverse in matcher.subgraph_monomorphisms_iter():
            guard(end)
            mapping=[next(u for u,r2 in inverse.items() if r2==r) for r in range(len(self.q))]
            if mapping_legal(self.identity,mapping):
                rank=rank_of(mapping,tables,base)
                if rank in allowed:
                    return {'mapping':mapping,'state':rank}
        return None


def run(method, identity, tables, base, budget):
    if method=='semantic':
        return diagnose_tables(identity,tables,base,budget)
    start=time.perf_counter();end=start+budget;engine=None
    try:
        if method=='whole_cp':
            result=consensus(lambda allowed:whole_query(identity,tables,base,allowed,end))
        elif method in ('materialized','vf2'):
            engine=(Materialized if method=='materialized' else VF2)(identity,tables,base,end)
            result=consensus(engine.query)
        else:
            options={'hall':method not in ('no_hall','plain_decomposition'),
                     'eager':method in ('eager_resources','plain_decomposition'),
                     'reuse':method not in ('no_query_reuse','plain_decomposition')}
            engine=Variant(identity,tables,base,end,**options)
            result=consensus(engine.query)
        guard(end)
    except Deadline:
        result=dict(label='UNKNOWN',reason='budget',certificate=False,mappings=[])
    except (MemoryError, RecursionError, ResourceLimit) as exc:
        result=dict(label='UNKNOWN',reason='resource_limit',certificate=False,mappings=[],detail=str(exc))
    # Policy limits in Variant use the same defaults as the frozen core.
    result.update(seconds=time.perf_counter()-start,route=method)
    if isinstance(engine,Projection):
        result.update(engine.stats,evidence=engine.evidence())
    if isinstance(engine,Materialized):
        result.update(configuration_count=sum(map(len,engine.configs)),enumeration_nodes=engine.nodes)
    if result['seconds']>budget:
        result.update(label='UNKNOWN',reason='deadline_overrun',certificate=False)
    return result
