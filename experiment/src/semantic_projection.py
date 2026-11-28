"""Shared obligation, ownership, oracle and Hall primitives for EG-ICAF."""
import time
from collections import Counter, defaultdict, deque

import networkx as nx
import numpy as np
from ortools.sat.python import cp_model

from diagnostic_engine import early_check, scoped_contradiction
from projection_engine import Deadline, Unsupported, graph_data, guard, sparse_diagnosis, vectors

S, U, V = 0, 1, 2
ANY, NON_S, NON_V = (S, V), (U, V), (S, U)
ONLY_S, ONLY_U, ONLY_V = (S, S), (U, U), (V, V)
INTERVALS = (ANY, NON_S, NON_V, ONLY_S, ONLY_U, ONLY_V)
RANK_LABELS = ['SATISFIES', 'UNKNOWN', 'VIOLATES']
LEGACY_TO_RANK = np.asarray([S, V, U], dtype=np.int8)


class ResourceLimit(Exception):
    pass


def stronger(interval, premise):
    return premise[0] <= interval[0] <= interval[1] <= premise[1]


def context_partition(allowed, contexts):
    """Coarsest rank quotient preserving target membership for these contexts."""
    groups = defaultdict(list)
    for rank in (S, U, V):
        key = tuple(max(rank, context) in allowed for context in sorted(contexts))
        groups[key].append(rank)
    return list(groups.values())


def goal_plans(allowed, base):
    """Each plan has a universal local interval and, optionally, one witness.

    Only ANY, NON_S, NON_V occur in the two queries used by diagnosis. The
    singleton plans also support independent state-set checking of the core.
    """
    allowed = frozenset(allowed)
    if not allowed <= {S, U, V}:
        raise ValueError('target states must use S=0,U=1,V=2')
    if not allowed:
        return []
    if allowed == {S, U, V}:
        return [(ANY, None)]
    if allowed == {S}:
        return [(ONLY_S, None)] if base == S else []
    if allowed == {U}:
        return [] if base == V else [(NON_V, None if base == U else ONLY_U)]
    if allowed == {V}:
        return [(ANY, None if base == V else ONLY_V)]
    if allowed == {S, U}:
        return [] if base == V else [(NON_V, None)]
    if allowed == {U, V}:
        return [(ANY, None if base >= U else NON_S)]
    return goal_plans({S}, base)+goal_plans({V}, base)  # {S,V}


class Projection:
    """Input-local oracle/cut state, shared across diagnosis target queries."""

    def __init__(self, identity, role_states, global_state, end, max_cuts=20000,
                 max_refinements=None, max_oracle_calls=200000,
                 hall=True):
        guard(end)
        self.identity, self.end = identity, end
        self.max_cuts, self.max_refinements = max_cuts, max_refinements
        self.max_oracle_calls = max_oracle_calls
        self.hall_enabled = hall
        self.g, self.q, self.anchors = graph_data(identity)
        self.n = len(self.g)
        if not set(self.anchors) <= set(self.q):
            raise Unsupported('anchor role outside query')
        if global_state not in (S, U, V):
            raise ValueError('global_state must use S=0,U=1,V=2')
        self.states = {}
        for role, values in role_states.items():
            if role not in self.q or len(values) != self.n or any(x not in (S, U, V) for x in values):
                raise ValueError('role predicate must give S=0,U=1,V=2 for every entity')
            self.states[role] = list(map(int, values))
        self.base = max([global_state]+[self.states[r][u] for r, u in self.anchors.items()
                                       if r in self.states])
        self.xyz = np.asarray(identity['candidate_xyz'])
        self.lengths = {(r, s): length for r, s, length, _ in identity['role_edges']}
        self.lengths.update({(s, r): value for (r, s), value in list(self.lengths.items())})
        self.anchor_consistent = all(self.compatible(r, self.anchors[r], s, self.anchors[s])
                                     for r, s in self.q.edges
                                     if r in self.anchors and s in self.anchors)
        self.components = [set(c) for c in nx.connected_components(
            self.q.subgraph(set(self.q)-set(self.anchors)))]
        self.role_component = {r: i for i, roles in enumerate(self.components) for r in roles}
        self.raw_domains = [self.initial_domains(roles) for roles in self.components]
        self.domains = [self.arc_consistent(roles, domains)
                        for roles, domains in zip(self.components, self.raw_domains)]
        self.supports = [set().union(*domains.values()) if domains else set()
                         for domains in self.domains]
        counts = Counter(u for support in self.supports for u in support)
        self.frontier = {u for u, count in counts.items() if count > 1}
        self.active = set()
        self.models, self.witnesses = {}, defaultdict(list)
        self.hall_candidate = None
        self.cuts, self.hall_cuts, self.trace = [], [], []
        self.stats = {'cp_calls': 0, 'local_oracle_calls': 0, 'master_calls': 0, 'master_proposals': 0,
                      'resource_cuts_learned': 0,
                      'hall_cuts_learned': 0, 'transferred_cut_applications': 0,
                      'validated_relaxation_witnesses': 0,
                      'witness_cache_hits': 0, 'refinements': 0,
                      'query_components': len(self.components),
                      'potential_conflict_entities': len(self.frontier),
                      'exposed_conflict_entities': 0,
                      'locally_checked_roles': len(self.states),
                      'configuration_tables_enumerated': False}

    def compatible(self, r, u, s, v):
        length = self.lengths[r, s]
        return self.g.has_edge(u, v) and (length is None or
            abs(np.linalg.norm(self.xyz[u]-self.xyz[v])-length) < self.identity['length_tolerance'])

    def initial_domains(self, roles):
        candidates = set(self.g)-set(self.anchors.values())
        domains = {}
        for r in roles:
            guard(self.end)
            domains[r] = {u for u in candidates if self.g.degree[u] >= self.q.degree[r]
                          and all(self.compatible(r, u, a, self.anchors[a])
                                  for a in set(self.q[r]) & set(self.anchors))}
        return domains

    def arc_consistent(self, roles, initial):
        domains = {r: set(values) for r, values in initial.items()}
        neighbors = {r: set(self.q[r]) & roles for r in roles}
        queue = deque((r, s) for r in roles for s in neighbors[r])
        while queue:
            guard(self.end)
            r, s = queue.popleft()
            values = {u for u in domains[r] if any(self.compatible(r, u, s, v)
                                                   for v in domains[s])}
            if values != domains[r]:
                domains[r] = values
                queue.extend((v, r) for v in neighbors[r] if v != s)
        return domains

    def solve(self, model, local=False):
        guard(self.end)
        if local and self.stats['local_oracle_calls'] >= self.max_oracle_calls:
            raise ResourceLimit('local oracle call policy')
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 20261028
        solver.parameters.max_time_in_seconds = max(1e-9, self.end-time.perf_counter())
        self.stats['cp_calls'] += 1
        self.stats['local_oracle_calls' if local else 'master_calls'] += 1
        status = solver.solve(model)
        guard(self.end)
        if status == cp_model.MODEL_INVALID:
            raise ValueError('Invalid internal obligation CP model')
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE, cp_model.INFEASIBLE):
            raise Deadline()
        return solver, status != cp_model.INFEASIBLE

    def local_model(self, i, interval):
        key = i, interval
        if key in self.models:
            return self.models[key]
        roles, domains = self.components[i], self.domains[i]
        model = cp_model.CpModel()
        ys = {}
        if any(not values for values in domains.values()):
            model.add_bool_or([])
        else:
            ys = {r: model.new_int_var_from_domain(cp_model.Domain.from_values(sorted(domains[r])), f'y{r}')
                  for r in sorted(roles)}
            model.add_all_different(list(ys.values()))
            for r, s in self.q.subgraph(roles).edges:
                guard(self.end)
                pairs = [(u, v) for u in sorted(domains[r]) for v in sorted(set(self.g[u]) & domains[s])
                         if self.compatible(r, u, s, v)]
                model.add_allowed_assignments([ys[r], ys[s]], pairs)
            # ANY imposes no diagnostic model or state enumeration at all.
            if interval != ANY:
                predicates = []
                for r in sorted(roles & set(self.states)):
                    var = model.new_int_var(S, V, f'predicate_{r}')
                    model.add_element(ys[r], self.states[r], var)
                    predicates.append(var)
                aggregate = model.new_int_var(S, V, 'local_diagnosis')
                model.add_max_equality(aggregate, predicates or [S])
                model.add(aggregate >= interval[0])
                model.add(aggregate <= interval[1])
        self.models[key] = {'model': model, 'ys': ys, 'bans': {}}
        return self.models[key]

    def oracle(self, i, interval, forbidden):
        """One existential query, or a core of positive resource-ban assumptions."""
        guard(self.end)
        forbidden = frozenset(forbidden)
        if not forbidden <= self.supports[i]:
            raise ValueError('forbidden entity outside component support')
        for witness in self.witnesses[i]:
            if interval[0] <= witness['state'] <= interval[1] and not forbidden & witness['footprint']:
                self.stats['witness_cache_hits'] += 1
                return {'sat': True, 'witness': witness}
        compiled = self.local_model(i, interval)
        model, ys, bans = compiled['model'], compiled['ys'], compiled['bans']
        for u in sorted(forbidden-set(bans)):
            var = model.new_bool_var(f'ban_{u}')
            bans[u] = var
            for r, y in ys.items():
                if u in self.domains[i][r]:
                    model.add(y != u).only_enforce_if(var)
        model.clear_assumptions()
        model.add_assumptions([bans[u] for u in sorted(forbidden)])
        solver, sat = self.solve(model, local=True)
        if sat:
            mapping = {r: solver.value(y) for r, y in ys.items()}
            rank = max([S]+[self.states[r][u] for r, u in mapping.items() if r in self.states])
            witness = {'mapping': mapping, 'state': rank, 'footprint': frozenset(mapping.values())}
            if not interval[0] <= rank <= interval[1] or forbidden & witness['footprint']:
                raise AssertionError('local oracle witness violates its obligation')
            self.witnesses[i].append(witness)
            return {'sat': True, 'witness': witness}
        indices = {bans[u].Index(): u for u in forbidden}
        core = frozenset(indices[index] for index in solver.sufficient_assumptions_for_infeasibility())
        return {'sat': False, 'core': core}

    def learn_failure(self, i, interval, core):
        """Keep the solver's sufficient core under its original semantic premise."""
        premise, core = interval, frozenset(core)
        minimal = False
        item = {'component': i, 'interval': premise, 'core': core,
                'subset_minimal': minimal}
        # Wider premise + smaller forbidden core dominates a narrower clause.
        if any(c['component'] == i and stronger(premise, c['interval']) and c['core'] <= core
               for c in self.cuts):
            raise AssertionError('master proposed an assignment excluded by an existing core')
        self.cuts = [c for c in self.cuts if not (c['component'] == i
                     and stronger(c['interval'], premise) and core <= c['core'])]
        self.cuts.append(item)
        self.stats['resource_cuts_learned'] += 1
        self.check_cut_limit()
        self.trace.append({'status': 'resource_obstruction', 'component': i,
                           'interval': list(premise), 'forbidden_core': sorted(core),
                           'subset_minimal': minimal})

    def check_cut_limit(self):
        if len(self.cuts)+len(self.hall_cuts) > self.max_cuts:
            raise ResourceLimit('learned cut policy')

    def hall_obstruction(self, obligations):
        """Necessary domains only: no local configuration materialization.

        Hall domains use directly replayable degree/anchor/length conditions and
        each predicate's upper bound. No unlogged AC deletion is trusted here.
        """
        self.hall_candidate = None
        domains = {}
        for i, initial in enumerate(self.raw_domains):
            hi = obligations[i][1]
            for r, values in initial.items():
                domains[r] = {u for u in values if r not in self.states or self.states[r][u] <= hi}
        owner = {}

        def augment(r, seen):
            guard(self.end)
            for u in sorted(domains[r]):
                if u not in seen:
                    seen.add(u)
                    if u not in owner or augment(owner[u], seen):
                        owner[u] = r
                        return True
            return False

        unmatched = [r for r in sorted(domains, key=lambda r: (len(domains[r]), r))
                     if not augment(r, set())]
        if not unmatched:
            self.hall_candidate = {**self.anchors, **{r: u for u, r in owner.items()}}
            return None
        roles, entities, queue = set(unmatched), set(), deque(unmatched)
        while queue:
            r = queue.popleft()
            for u in domains[r]:
                entities.add(u)
                if u in owner and owner[u] not in roles:
                    roles.add(owner[u])
                    queue.append(owner[u])
        assert len(roles) > len(entities)
        components = sorted({self.role_component[r] for r in roles})
        # Only upper bounds were used; lower-bound premises are safely dropped.
        premises = {i: (S, obligations[i][1]) for i in components}
        return {'roles': sorted(roles), 'entities': sorted(entities),
                'domains': {r: sorted(domains[r]) for r in sorted(roles)},
                'premises': premises, 'demand': len(roles), 'capacity': len(entities)}

    def validate_relaxation_candidate(self, obligations, allowed):
        """A matching is only a candidate until EVERY original relation passes."""
        mapping = self.hall_candidate
        if mapping is None or set(mapping) != set(self.q) or len(set(mapping.values())) != len(mapping):
            return None
        for r, s in self.q.edges:
            guard(self.end)
            if not self.compatible(r, mapping[r], s, mapping[s]):
                return None
        ranks = []
        for roles, interval in zip(self.components, obligations):
            rank = max([S]+[self.states[r][mapping[r]] for r in roles if r in self.states])
            if not interval[0] <= rank <= interval[1]:
                return None
            ranks.append(rank)
        rank = max([self.base]+ranks)
        if rank not in allowed:
            return None
        # Anchors were inserted unchanged; initial matching domains exclude them.
        self.stats['validated_relaxation_witnesses'] += 1
        return {'mapping': [mapping[r] for r in range(len(self.q))], 'state': rank}

    def master(self, default, witness):
        self.stats['master_proposals'] += 1
        guard(self.end)
        # With no exposed ownership bits and no witness selector, the master
        # has only a fixed assignment. Evaluate its learned clauses directly.
        if not self.active and witness is None:
            if any(not c['core'] and stronger(default, c['interval']) for c in self.cuts):
                return None
            if any(all(stronger(default, premise) for premise in c['premises'].values())
                   for c in self.hall_cuts):
                return None
            return [default for _ in self.components], [set() for _ in self.components]
        model = cp_model.CpModel()
        options = [[default] if witness is None else [default, witness]
                   for _ in self.components]
        modes = [model.new_int_var(0, len(values)-1, f'mode{i}') for i, values in enumerate(options)]
        selectors = {}

        def eq(i, k):
            if (i, k) not in selectors:
                bit = model.new_bool_var(f'mode{i}_is_{k}')
                model.add(modes[i] == k).only_enforce_if(bit)
                model.add(modes[i] != k).only_enforce_if(bit.Not())
                selectors[i, k] = bit
            return selectors[i, k]

        def escape(i, premise):
            covered = [k for k, option in enumerate(options[i]) if stronger(option, premise)]
            if not covered:
                return True  # Cut premise is inactive in this query.
            if len(covered) == len(options[i]):
                return False
            assert len(covered) == 1  # At most two obligation options per plan.
            return eq(i, covered[0]).Not()

        if witness is not None:
            model.add_exactly_one([eq(i, 1) for i in range(len(self.components))])
        available = {}
        for u in sorted(self.active):
            variables = []
            for i, support in enumerate(self.supports):
                if u in support:
                    var = model.new_bool_var(f'available_{i}_{u}')
                    available[i, u] = var
                    variables.append(var)
            model.add_at_most_one(variables)
        for cut in self.cuts:
            i, premise = cut['component'], cut['interval']
            skip = escape(i, premise)
            if skip is True:
                continue
            literals = [available[i, u] for u in cut['core']]
            if skip is not False:
                literals.append(skip)
            model.add_bool_or(literals)
            if any(option != premise and stronger(option, premise) for option in options[i]):
                self.stats['transferred_cut_applications'] += 1
        for cut in self.hall_cuts:
            literals, inactive = [], False
            for i, premise in cut['premises'].items():
                skip = escape(i, premise)
                if skip is True:
                    inactive = True
                    break
                if skip is not False:
                    literals.append(skip)
            if not inactive:
                model.add_bool_or(literals)
        solver, sat = self.solve(model)
        if not sat:
            return None
        obligations = [options[i][solver.value(mode)] for i, mode in enumerate(modes)]
        forbidden = [{u for u in self.active & self.supports[i] if not solver.value(available[i, u])}
                     for i in range(len(self.components))]
        return obligations, forbidden

    def retain_hall(self, hall):
        self.hall_cuts.append(hall)
        self.stats['hall_cuts_learned'] += 1
        self.check_cut_limit()

    def query_plan(self, default, witness, allowed):
        while True:
            guard(self.end)
            assignment = self.master(default, witness)
            if assignment is None:
                self.trace.append({'status': 'master_UNSAT', 'allowed': sorted(allowed)})
                return None
            obligations, forbidden = assignment
            if self.hall_enabled:
                hall = self.hall_obstruction(obligations)
                if hall is not None:
                    self.retain_hall(hall)
                    self.trace.append({'status': 'conditional_Hall', 'allowed': sorted(allowed),
                                       'demand': hall['demand'], 'capacity': hall['capacity']})
                    continue
                lifted = self.validate_relaxation_candidate(obligations, allowed)
                if lifted is not None:
                    self.trace.append({'status': 'validated_matching_SAT', 'allowed': sorted(allowed),
                                       'obligations': [list(x) for x in obligations]})
                    return lifted
            selected = []
            for i, interval in enumerate(obligations):
                answer = self.oracle(i, interval, forbidden[i])
                if not answer['sat']:
                    self.learn_failure(i, interval, answer['core'])
                    break
                selected.append(answer['witness'])
            else:
                mapping, used, collisions = dict(self.anchors), set(), set()
                for item in selected:
                    collisions.update(used & item['footprint'])
                    used.update(item['footprint'])
                    mapping.update(item['mapping'])
                if not collisions:
                    rank = max([self.base]+[item['state'] for item in selected])
                    if rank not in allowed:
                        raise AssertionError('goal obligations do not imply target membership')
                    self.trace.append({'status': 'lifted_SAT', 'allowed': sorted(allowed),
                                       'obligations': [list(x) for x in obligations]})
                    return {'mapping': [mapping[r] for r in range(len(self.q))], 'state': rank}
                if not collisions <= self.frontier-self.active:
                    raise AssertionError('collision must be an unexposed shared resource')
                if self.max_refinements is not None and self.stats['refinements'] >= self.max_refinements:
                    raise ResourceLimit('interface refinement policy')
                self.active.update(collisions)
                self.stats['refinements'] += 1
                self.stats['exposed_conflict_entities'] = len(self.active)
                self.trace.append({'status': 'expose_collision', 'entities': sorted(collisions)})

    def query(self, allowed):
        guard(self.end)
        if not self.anchor_consistent:
            return None
        for default, witness in goal_plans(allowed, self.base):
            result = self.query_plan(default, witness, allowed)
            if result is not None:
                return result
        return None

    def evidence(self):
        return {'resource_obstructions': [dict(component=c['component'], interval=list(c['interval']),
                    core=sorted(c['core']), subset_minimal=c['subset_minimal']) for c in self.cuts],
                'hall_obstructions': self.hall_cuts,
                'scope': 'resource cores trust local CP; Hall arguments replay necessary domains; not formal UNSAT proofs'}


def verify_hall(identity, role_states, certificate):
    """Recompute necessary domains without invoking Projection, CP, or AC."""
    try:
        n = len(identity['candidate_xyz'])
        xyz = np.asarray(identity['candidate_xyz'])
        adjacency = [set() for _ in range(n)]
        for u, v in identity['candidate_edges']:
            adjacency[u].add(v)
            adjacency[v].add(u)
        qadj = [set() for _ in range(identity['role_count'])]
        lengths = {}
        for r, s, length, _ in identity['role_edges']:
            qadj[r].add(s); qadj[s].add(r)
            lengths[r, s] = lengths[s, r] = length
        anchors = {}
        for role, point in identity['registered_positions'].items():
            found = [u for u in range(n) if max(abs(xyz[u]-point)) < identity['coordinate_tolerance']]
            if len(found) != 1:
                return False
            anchors[int(role)] = found[0]
        if len(set(anchors.values())) != len(anchors):
            return False
        graph = nx.Graph(); graph.add_nodes_from(range(identity['role_count']))
        graph.add_edges_from(lengths)
        components = [set(c) for c in nx.connected_components(graph.subgraph(set(graph)-set(anchors)))]
        indices = {r: i for i, comp in enumerate(components) for r in comp}
        premises = {int(i): tuple(value) for i, value in certificate['premises'].items()}
        roles = certificate['roles']; entities = set(certificate['entities'])
        if len(roles) != len(set(roles)) or len(entities) != len(certificate['entities']):
            return False
        if any(u not in range(n) for u in entities) or not len(roles) > len(entities):
            return False
        for r in roles:
            if r not in indices or indices[r] not in premises:
                return False
            interval = premises[indices[r]]
            if interval not in INTERVALS or interval[0] != S:
                return False
            necessary = set()
            for u in set(range(n))-set(anchors.values()):
                if len(adjacency[u]) < len(qadj[r]):
                    continue
                if r in role_states and role_states[r][u] > interval[1]:
                    continue
                valid = True
                for a in qadj[r] & set(anchors):
                    length = lengths[r, a]
                    if anchors[a] not in adjacency[u] or (length is not None and
                        abs(np.linalg.norm(xyz[u]-xyz[anchors[a]])-length) >= identity['length_tolerance']):
                        valid = False; break
                if valid:
                    necessary.add(u)
            claimed = certificate['domains'].get(r, certificate['domains'].get(str(r)))
            if claimed is None or set(claimed) != necessary or not necessary <= entities:
                return False
        return certificate['demand'] == len(roles) and certificate['capacity'] == len(entities)
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def diagnose_tables(identity, role_states, global_state=S, timeout=1., **limits):
    """Compatibility name for the sole public EG-ICAF method."""
    from structural_adapter import diagnose_tables as current
    return current(identity, role_states, global_state, timeout, **limits)


def diagnose(identity, task, timeout=1., scope=True, fallback=True, **limits):
    from structural_adapter import diagnose as current
    return current(identity, task, timeout, scope, fallback, **limits)
