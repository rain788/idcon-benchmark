"""Independent CNF encoding of IdCon identity spaces (revision R2).

Written for revision R2 without reusing any code from experiment/src: it reads
the task JSON files directly and implements the semantics of Section 3 of the
paper from scratch. It is used by
  * independent/idcheck.py  - the independent reference check (CaDiCaL with
    DRAT proofs checked by drat-trim; witnesses replayed by check_identity);
  * src/sat_baseline.py     - the SAT consensus baseline (in-process CaDiCaL).

Semantics (paper, Section 3). An identity y maps roles injectively to
entities with y(r) = a(r) for anchored roles, y(r) in D_r for roles with a
unary domain, {y(r), y(s)} an observed edge for every pattern edge, and
| ||x_y(r) - x_y(s)|| - l | < eps for metric pattern edges. The state of y is
T(y) = max(t0, max_{r checked} p_r(y(r))) with S=0 < U=1 < V=2.
"""
import json
import math
from pathlib import Path

S, U, V = 0, 1, 2


def load_task(identity_path, tables_path):
    identity = json.loads(Path(identity_path).read_text())
    observed = json.loads(Path(tables_path).read_text())
    tables = {int(r): list(v) for r, v in observed['role_states'].items()}
    return identity, tables, int(observed.get('global_state', 0))


class Space:
    """Pre-processed identity space: adjacency, anchors, domains."""

    def __init__(self, identity):
        self.identity = identity
        self.n = len(identity['candidate_xyz'])
        self.k = int(identity['role_count'])
        self.xyz = [tuple(map(float, p)) for p in identity['candidate_xyz']]
        self.adj = [set() for _ in range(self.n)]
        for a, b in identity['candidate_edges']:
            if a != b:
                self.adj[a].add(b)
                self.adj[b].add(a)
        self.eps = float(identity['length_tolerance'])
        # pattern edges, merged per unordered role pair (a metric edge and a
        # plain edge on the same pair both have to hold)
        self.pedges = {}
        for r, s, length, _ in identity['role_edges']:
            if r == s:
                raise ValueError('self-loop in pattern')
            key = (min(r, s), max(r, s))
            self.pedges.setdefault(key, []).append(None if length is None else float(length))
        self.nbrs = [set() for _ in range(self.k)]
        for r, s in self.pedges:
            self.nbrs[r].add(s)
            self.nbrs[s].add(r)
        tol = float(identity['coordinate_tolerance'])
        self.anchor = {}
        for r, p in identity.get('registered_positions', {}).items():
            hits = [u for u in range(self.n)
                    if max(abs(self.xyz[u][i] - float(p[i])) for i in range(3)) < tol]
            if len(hits) != 1:
                raise ValueError('anchor not unique')
            self.anchor[int(r)] = hits[0]
        self.unary = {int(r): set(v) for r, v in identity.get('role_domains', {}).items()}

    def dist(self, u, v):
        a, b = self.xyz[u], self.xyz[v]
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)

    def edge_ok(self, r, s, u, v):
        if v not in self.adj[u]:
            return False
        for length in self.pedges[(min(r, s), max(r, s))]:
            if length is not None and not abs(self.dist(u, v) - length) < self.eps:
                return False
        return True

    def base_domains(self, tick=None):
        """Domains from anchors, unary domains and the degree bound only."""
        deg_q = [len(self.nbrs[r]) for r in range(self.k)]
        anchored = set(self.anchor.values())
        doms = []
        for r in range(self.k):
            if r in self.anchor:
                d = {self.anchor[r]}
            else:
                d = {u for u in range(self.n) if u not in anchored}
            if r in self.unary:
                d &= self.unary[r]
            d = {u for u in d if len(self.adj[u]) >= deg_q[r]}
            doms.append(d)
            if tick:
                tick()
        return doms

    def arc_consistency(self, doms):
        """Remove values without support on some pattern edge (sound pruning)."""
        doms = [set(d) for d in doms]
        queue = [(r, s) for r in range(self.k) for s in self.nbrs[r]]
        inq = set(queue)
        while queue:
            r, s = queue.pop()
            inq.discard((r, s))
            ds = doms[s]
            keep = {u for u in doms[r] if any(v in ds and self.edge_ok(r, s, u, v) for v in self.adj[u])}
            if len(keep) != len(doms[r]):
                doms[r] = keep
                if not keep:
                    return doms
                for t in self.nbrs[r]:
                    if t != s and (t, r) not in inq:
                        queue.append((t, r))
                        inq.add((t, r))
        return doms


def check_identity(space, tables, t0, y):
    """Replay an identity against the raw task (no CNF involved); return T(y) or None."""
    if len(y) != space.k or len(set(y)) != space.k:
        return None
    if any(not (0 <= u < space.n) for u in y):
        return None
    for r, u in space.anchor.items():
        if y[r] != u:
            return None
    for r, d in space.unary.items():
        if y[r] not in d:
            return None
    for (r, s) in space.pedges:
        if not space.edge_ok(r, s, y[r], y[s]):
            return None
    return max([t0] + [tables[r][y[r]] for r in tables])


class CNF:
    def __init__(self):
        self.nvars = 0
        self.clauses = []

    def var(self):
        self.nvars += 1
        return self.nvars

    def add(self, clause):
        self.clauses.append(clause)

    def amo(self, lits):
        """At-most-one, sequential counter (Sinz 2005) for long lists."""
        if len(lits) <= 1:
            return
        if len(lits) <= 5:
            for i in range(len(lits)):
                for j in range(i + 1, len(lits)):
                    self.add([-lits[i], -lits[j]])
            return
        prev = self.var()
        self.add([-lits[0], prev])
        for i in range(1, len(lits) - 1):
            cur = self.var()
            self.add([-lits[i], cur])
            self.add([-prev, cur])
            self.add([-lits[i], -prev])
            prev = cur
        self.add([-lits[-1], -prev])

    def dimacs(self):
        out = [f'p cnf {self.nvars} {len(self.clauses)}']
        out += [' '.join(map(str, c)) + ' 0' for c in self.clauses]
        return '\n'.join(out) + '\n'


def encode(space, doms, tick=None):
    """Base identity-space CNF over pre-filtered domains. Returns (cnf, x) where
    x[(r, u)] is the variable of y(r) = u; None if some domain is empty."""
    if any(not d for d in doms):
        return None, None
    cnf = CNF()
    x = {}
    for r in range(space.k):
        for u in sorted(doms[r]):
            x[(r, u)] = cnf.var()
    by_entity = {}
    for r in range(space.k):
        if tick:
            tick()
        lits = [x[(r, u)] for u in sorted(doms[r])]
        cnf.add(lits)
        cnf.amo(lits)
        for u in doms[r]:
            by_entity.setdefault(u, []).append(x[(r, u)])
    for i, (u, lits) in enumerate(by_entity.items()):
        cnf.amo(sorted(lits))
        if tick and i % 512 == 0:
            tick()
    for (r, s) in space.pedges:
        for a, b in ((r, s), (s, r)):
            db = doms[b]
            if tick:
                tick()
            for u in sorted(doms[a]):
                support = [x[(b, v)] for v in sorted(space.adj[u]) if v in db and space.edge_ok(a, b, u, v)]
                cnf.add([-x[(a, u)]] + support)
    return cnf, x


def state_domains(doms, tables, state):
    """Restrict domains of checked roles to entities whose state is <= `state`."""
    out = [set(d) for d in doms]
    for r, values in tables.items():
        out[r] = {u for u in out[r] if values[u] <= state}
    return out


def exact_state_cnf(space, tables, t0, state, use_ac=True):
    """CNF whose models are exactly the identities with T(y) == state.
    Returns (cnf, x) or (None, None) when the query is trivially unsatisfiable
    (an empty domain, or state < t0)."""
    if state < t0:
        return None, None
    doms = state_domains(space.base_domains(), tables, state)
    if use_ac:
        doms = space.arc_consistency(doms)
    cnf, x = encode(space, doms)
    if cnf is None:
        return None, None
    if state > t0:
        hit = [x[(r, u)] for r, values in tables.items() for u in sorted(doms[r]) if values[u] == state]
        if not hit:
            return None, None
        cnf.add(hit)
    return cnf, x


def decode(space, x, model):
    pos = set(l for l in model if l > 0)
    y = [None] * space.k
    for (r, u), var in x.items():
        if var in pos:
            y[r] = u
    return y
