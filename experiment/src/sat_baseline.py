"""Revision R2 baseline: SAT consensus with CaDiCaL 2.1.3 (one process per query).

The identity space is encoded once by independent/cnf_encoding.py (pattern
edges as support clauses, AllDifferent as at-most-one per entity, one value per
role; anchors, unary domains, degree bound and metric edges applied while
building the domains). Selector literals then express the two-query reduction
of Section 3 as unit clauses added to the base formula, one CaDiCaL process per
query (killed at the budget, like LAD2025 and Glasgow):
  exists T(y) in {S,U,V}            (no assumption)
  exists T(y) <= h                  (assume a_h: checked roles avoid states > h)
  exists T(y) >= l                  (assume b_l: some checked role has state >= l)
Every positive answer carries a witness that the benchmark replays; negative
answers are solver claims without a proof, as for every other method.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CADICAL = Path(os.environ.get('IDCON_CADICAL', ROOT / 'third_party/build/cadical'))
TMP = '/dev/shm' if os.path.isdir('/dev/shm') else None
sys.path.insert(0, str(ROOT / 'independent'))
from cnf_encoding import S, U, V, Space, encode, decode  # noqa: E402


class Budget(Exception):
    pass


def diagnose_tables(identity, tables, base, budget):
    start = time.perf_counter()
    end = start + budget
    mappings = []

    def left():
        rest = end - time.perf_counter()
        if rest <= 0:
            raise Budget()
        return rest

    try:
        space = Space(identity)
        left()
        doms = space.base_domains(tick=left)
        left()
        cnf, x = encode(space, doms, tick=left)
        left()
        if cnf is None:
            return dict(label='UNKNOWN', reason='identity_inconsistent', certificate=True,
                        mappings=[], seconds=time.perf_counter() - start)
        a = {h: cnf.var() for h in (S, U)}      # a_h : T(y) <= h
        b = {l: cnf.var() for l in (U, V)}      # b_l : T(y) >= l
        for h, sel in a.items():
            for r, values in tables.items():
                for u in doms[r]:
                    if values[u] > h:
                        cnf.add([-sel, -x[(r, u)]])
        for l, sel in b.items():
            cnf.add([-sel] + [x[(r, u)] for r, values in tables.items() for u in sorted(doms[r])
                              if values[u] >= l])
        left()
        base_text = cnf.dimacs().split('\n', 1)[1]

        def ask(assumptions):
            rest = left()
            units = ''.join(f'{lit} 0\n' for lit in assumptions)
            with tempfile.TemporaryDirectory(dir=TMP) as tmp:
                f = Path(tmp) / 'q.cnf'
                f.write_text(f'p cnf {cnf.nvars} {len(cnf.clauses) + len(assumptions)}\n' + base_text + units)
                rest = left()
                try:
                    run = subprocess.run([str(CADICAL), '-q', str(f)], capture_output=True, text=True,
                                         timeout=rest)
                except subprocess.TimeoutExpired:
                    raise Budget()
            if run.returncode == 20:
                return None
            if run.returncode != 10:
                raise RuntimeError(f'CaDiCaL exit code {run.returncode}')
            model = [int(v) for line in run.stdout.splitlines() if line.startswith('v ')
                     for v in line[2:].split()]
            y = decode(space, x, model)
            state = max([base] + [tables[r][y[r]] for r in tables])
            return y, state

        first = ask([])
        if first is None:
            result = dict(label='UNKNOWN', reason='identity_inconsistent', certificate=True)
        else:
            mappings.append(first[0])
            state = first[1]
            if state == V and base == V:
                result = dict(label='VIOLATES', reason='global_state_violates', certificate=True)
            elif state == U:
                result = dict(label='UNKNOWN', reason='missing_evidence_witness', certificate=True)
            else:
                other = ask([a[U]]) if state == V else ask([b[U]])
                if other is None:
                    result = dict(label=['SATISFIES', 'UNKNOWN', 'VIOLATES'][state],
                                  reason='counterexample_excluded', certificate=True)
                else:
                    mappings.append(other[0])
                    result = dict(label='UNKNOWN', reason='conflicting_identity_witnesses',
                                  certificate=True)
    except Budget:
        result = dict(label='UNKNOWN', reason='budget', certificate=False)
    except RuntimeError as exc:
        result = dict(label='UNKNOWN', reason='runtime_error', certificate=False, detail=str(exc)[:300])
    except ValueError as exc:
        result = dict(label='UNKNOWN', reason='identity_binding_unsupported', certificate=False,
                      detail=str(exc))
    result['mappings'] = mappings
    result['seconds'] = time.perf_counter() - start
    return result
