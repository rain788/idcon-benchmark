"""Independent reference check (revision R2).

For each selected task, decide the three exact-state queries T(y) = S, U, V
with an encoding written from scratch (cnf_encoding.py), CaDiCaL and drat-trim:
  * SAT   -> the model is decoded and replayed against the raw task JSON by
             cnf_encoding.check_identity (no CNF involved), which must return
             exactly the queried state;
  * UNSAT -> decided on the encoding WITHOUT this file's arc-consistency
             pruning; CaDiCaL writes a DRAT proof, which drat-trim must verify.
             Exceptions needing no search: a role domain that is empty from
             anchors, unary domains, the degree bound and the tables alone,
             or no entity observed in the queried state (empty disjunction);
  * other -> 'UNRESOLVED' (time limit or proof check not finished).
The label follows Section 3 (Empty / Satisfies / Violates / Unknown). Nothing
from experiment/src is imported, and no reference or prediction is read: the
comparison with the frozen references is done afterwards by compare().

usage: python idcheck.py run SAMPLE.json OUT.jsonl [solve_s] [check_s]
       python idcheck.py compare OUT.jsonl
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cnf_encoding import (S, U, V, Space, load_task, exact_state_cnf, decode,
                          check_identity, state_domains)

ROOT = HERE.parent
CADICAL = Path(os.environ.get('IDCON_CADICAL', ROOT / 'third_party/build/cadical'))
DRAT_TRIM = Path(os.environ.get('IDCON_DRAT_TRIM', ROOT / 'third_party/build/drat-trim'))
TMP = '/dev/shm' if os.path.isdir('/dev/shm') else None


def _cadical(cnf, solve_s, check_s, proof_wanted):
    with tempfile.TemporaryDirectory(dir=TMP) as tmp:
        f = Path(tmp) / 'q.cnf'
        proof = Path(tmp) / 'q.drat'
        f.write_text(cnf.dimacs())
        cmd = [str(CADICAL), '-q'] + (['--binary=true', str(f), str(proof)] if proof_wanted else [str(f)])
        t = time.perf_counter()
        try:
            run = subprocess.run(cmd, capture_output=True, text=True, timeout=solve_s)
        except subprocess.TimeoutExpired:
            return dict(rc='timeout', solve_s=solve_s)
        info = dict(rc=run.returncode, solve_s=round(time.perf_counter() - t, 2),
                    vars=cnf.nvars, clauses=len(cnf.clauses))
        if run.returncode == 10:
            info['model'] = [int(v) for line in run.stdout.splitlines() if line.startswith('v ')
                             for v in line[2:].split()]
        if run.returncode == 20 and proof_wanted:
            t = time.perf_counter()
            try:
                chk = subprocess.run([str(DRAT_TRIM), str(f), str(proof), '-t', str(int(check_s))],
                                     capture_output=True, text=True, timeout=check_s + 30)
                info['verified'] = 's VERIFIED' in chk.stdout
            except subprocess.TimeoutExpired:
                info['verified'] = None
            info['check_s'] = round(time.perf_counter() - t, 2)
            info['proof_bytes'] = proof.stat().st_size
        return info


def solve_state(space, tables, t0, state, solve_s, check_s):
    """Search for a witness on the arc-consistent encoding (fast); certify a
    negative answer on the encoding WITHOUT arc consistency, so that the DRAT
    proof does not depend on this file's pruning code."""
    t = time.perf_counter()
    if state < t0:
        return dict(status='UNSAT', how='below_global_state')
    raw = state_domains(space.base_domains(), tables, state)
    if any(not d for d in raw):
        # an empty domain read directly off anchors, unary domains, the degree
        # bound and the observation tables: no search, no proof needed
        return dict(status='UNSAT', how='empty_domain')
    cnf, x = exact_state_cnf(space, tables, t0, state, use_ac=True)
    enc = round(time.perf_counter() - t, 2)
    if cnf is not None:
        info = _cadical(cnf, solve_s, check_s, proof_wanted=False)
        if info['rc'] == 10:
            y = decode(space, x, info['model'])
            if check_identity(space, tables, t0, y) != state:
                return dict(status='ERROR', how='witness_replay_failed')
            return dict(status='SAT', how='witness_replayed', encode_s=enc, solve_s=info['solve_s'])
        if info['rc'] == 'timeout':
            return dict(status='UNRESOLVED', how='solve_timeout_ac', encode_s=enc)
    # negative on the pruned encoding (or pruning emptied a domain): certify on
    # the unpruned encoding with a checked DRAT proof
    cnf, x = exact_state_cnf(space, tables, t0, state, use_ac=False)
    if cnf is None:
        # domains are non-empty, so the empty part is the disjunction 'some
        # checked role sits on an entity observed `state`': no such entity
        return dict(status='UNSAT', how='no_entity_with_state')
    info = _cadical(cnf, solve_s, check_s, proof_wanted=True)
    base = dict(encode_s=enc, solve_s=info.get('solve_s'), check_s=info.get('check_s'),
                vars=info.get('vars'), clauses=info.get('clauses'), proof_bytes=info.get('proof_bytes'))
    if info['rc'] == 10:
        return dict(status='ERROR', how='pruned_unsat_but_raw_sat', **base)
    if info['rc'] == 'timeout':
        return dict(status='UNRESOLVED', how='solve_timeout_raw', **base)
    if info['rc'] != 20:
        return dict(status='ERROR', how=f"cadical_rc_{info['rc']}", **base)
    if info.get('verified'):
        return dict(status='UNSAT', how='drat_verified', **base)
    return dict(status='UNSAT_UNCHECKED', how='proof_check_timeout' if info.get('verified') is None
                else 'proof_not_verified', **base)


def label_of(states):
    sat = [s for s in (S, U, V) if states[s]['status'] == 'SAT']
    unres = [s for s in (S, U, V) if states[s]['status'] not in ('SAT', 'UNSAT')]
    if U in sat or (S in sat and V in sat):
        return 'UNKNOWN'
    if unres:
        return 'UNRESOLVED'
    if not sat:
        return 'EMPTY'
    return 'SATISFIES' if sat == [S] else 'VIOLATES'


def run(sample_path, out_path, solve_s=600, check_s=1200):
    sample = json.loads(Path(sample_path).read_text())
    out = Path(out_path)
    done = set()
    if out.exists():
        done = {json.loads(l)['task_id'] for l in out.read_text().splitlines() if l.strip()}
    with out.open('a') as stream:
        for item in sample:
            if item['task_id'] in done:
                continue
            identity, tables, t0 = load_task(ROOT / item['identity_file'], ROOT / item['tables_file'])
            space = Space(identity)
            t = time.perf_counter()
            states = {}
            for s in (S, U, V):
                states[s] = solve_state(space, tables, t0, s, solve_s, check_s)
                states[s].pop('witness', None)
            row = dict(task_id=item['task_id'], label=label_of(states),
                       states={str(k): v for k, v in states.items()},
                       seconds=round(time.perf_counter() - t, 1))
            stream.write(json.dumps(row) + '\n')
            stream.flush()
            print('IDCHECK', item['task_id'], row['label'], row['seconds'], flush=True)


def compare(out_path, *ref_paths):
    rows = [json.loads(l) for l in Path(out_path).read_text().splitlines() if l.strip()]
    ref = {}
    for p in ref_paths:
        for l in Path(p).read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                ref[r['task_id']] = r['label']
    agree = sum(1 for r in rows if r['label'] == ref.get(r['task_id']))
    unres = sum(1 for r in rows if r['label'] == 'UNRESOLVED')
    dis = [(r['task_id'], r['label'], ref.get(r['task_id'])) for r in rows
           if r['label'] not in ('UNRESOLVED',) and r['label'] != ref.get(r['task_id'])]
    print(json.dumps(dict(tasks=len(rows), agree=agree, unresolved=unres, disagree=dis), indent=1))


if __name__ == '__main__':
    if sys.argv[1] == 'run':
        run(sys.argv[2], sys.argv[3], *(float(a) for a in sys.argv[4:6]))
    elif sys.argv[1] == 'compare':
        compare(*sys.argv[2:])
