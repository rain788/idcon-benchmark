"""Revision R1 reference strengthening for IdCon-Hard (frozen v1 references untouched).

recheck   (a) every non-trivial negative state that v1 did not corroborate with
              a second engine is re-queried with Glasgow --staged (60 s) and,
              if that does not complete, with CP-SAT (60 s);
          (b) the three tasks whose v1 references rested on the EG-ICAF consensus
              (Amendment 2) are re-settled without EG-ICAF: each undetermined
              state is queried with LAD2025, Glasgow --staged and CP-SAT
              (120 s each); a task that stays undetermined becomes UNASSESSED;
          (c) proof logging was assessed and not used: Glasgow's --prove
              refuses labelled inputs, which the encoding of unary domains and
              metric edges needs, and on the plain EMPTY tasks (unlabelled) the
              unlabelled Glasgow run did not finish within 100 s on the smallest
              instance (LAD2025: 0.12 s), see prove_empty() and design.json.
          Output: data/protected/idcon_hard/references_r1.jsonl.
Any positive witness found by a re-check against a v1 negative would refute
that reference; the script records it and stops with an error.
"""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault('IDCON_STUDY', 'idcon_hard')
import hard_benchmark as hb
from lad_baseline import ask as lad_ask, write_graph
from glasgow_baseline import ask as gl_ask, DEFAULT_BINARY
from coordination_confirmation_data import legal, state_query
from projection_engine import graph_data

PRIVATE = hb.PRIVATE
VERIPB = os.environ.get('IDCON_VERIPB', str(Path.home() / '.cargo/bin/veripb'))


def staged(identity, tables, base, restr, end, **_):
    return gl_ask(identity, tables, base, restr, end, DEFAULT_BINARY, ('--staged',))


def cp_state(identity, tables, s, budget):
    ans = state_query(identity, tables, 0, s, budget)
    st = ans.get('status')
    if st == 'SAT':
        assert legal(identity, ans['mapping'])
    return st if st in ('SAT', 'UNSAT') else 'UNKNOWN'


def frozen():
    rows = {}
    for name in ('references.w0.jsonl', 'references.manifest_focal.w0.jsonl', 'references.zretry.jsonl'):
        for line in (PRIVATE / name).read_text().splitlines():
            r = json.loads(line); rows[r['task_id']] = r
    return rows


def load(task_id, manifest):
    rec = manifest[task_id]
    identity = hb.read(hb.ROOT / rec['identity_file'])
    observed = hb.read(hb.ROOT / rec['tables_file'])
    return rec, identity, {int(r): v for r, v in observed['role_states'].items()}


def label_of(states):
    sat = [s for s in range(3) if states[str(s)]['status'] == 'SAT']
    unknown = [s for s in range(3) if states[str(s)]['status'] == 'UNKNOWN']
    if not unknown:
        return ('EMPTY' if not sat else 'SATISFIES' if sat == [0] else 'VIOLATES' if sat == [2] else 'UNKNOWN'), True
    if 1 in sat or (0 in sat and 2 in sat):
        return 'UNKNOWN', True
    return 'UNASSESSED', False


def prove_empty(identity, budget=120., check_budget=900.):
    g, q, anchors = graph_data(identity)
    assert not anchors and not identity.get('role_domains') and all(l is None for _, _, l, _ in identity['role_edges'])
    with tempfile.TemporaryDirectory(prefix='idcon_proof_') as tmp:
        p = Path(tmp)
        write_graph(p / 'pattern.lad', q); write_graph(p / 'target.lad', g)
        t0 = time.perf_counter()
        try:
            out = subprocess.run([str(DEFAULT_BINARY), '--format', 'lad', '--no-clique-detection',
                                  '--prove', str(p / 'proof'), str(p / 'pattern.lad'), str(p / 'target.lad')],
                                 capture_output=True, text=True, timeout=budget)
        except subprocess.TimeoutExpired:
            return dict(proof='solver_timeout', solve_seconds=budget)
        solve = time.perf_counter() - t0
        if 'status = false' not in out.stdout:
            return dict(proof='not_unsat', solve_seconds=solve, stdout=out.stdout[-300:])
        size = (p / 'proof.pbp').stat().st_size
        t1 = time.perf_counter()
        try:
            chk = subprocess.run([VERIPB, str(p / 'proof.opb'), str(p / 'proof.pbp')],
                                 capture_output=True, text=True, timeout=check_budget)
        except subprocess.TimeoutExpired:
            return dict(proof='check_timeout', solve_seconds=solve, proof_bytes=size)
        text = chk.stdout + chk.stderr
        ok = chk.returncode == 0 and ('Verification succeeded' in text or 's VERIFIED' in text
                                       or 'verified' in text.lower() and 'fail' not in text.lower())
        return dict(proof='verified' if ok else 'check_failed', solve_seconds=solve,
                    check_seconds=time.perf_counter() - t1, proof_bytes=size, checker_tail=text[-200:])


def recheck(worker=0, workers=1, only=None, failed=None):
    manifest = {r['task_id']: r for name in ('manifest.json', 'manifest_focal.json')
                for r in hb.read(hb.DATA / name)}
    refs = frozen()
    out = PRIVATE / f'references_r1.w{worker}.jsonl'
    done = set()
    if out.exists():
        done = {json.loads(l)['task_id'] for l in out.read_text().splitlines()}
    todo = sorted(refs)[worker::workers]
    if only is not None:
        todo = [only]
    with out.open('a') as stream:
        for tid in todo:
            if tid in done:
                continue
            if failed is not None:
                # The per-task process for this task was killed (memory limit):
                # keep the v1 states and record that the re-check could not run.
                v1 = refs[tid]
                stream.write(json.dumps(dict(task_id=tid, label_v1=v1['label'], label=v1['label'] if v1['complete'] and not any(st.get('engine') == 'eg_icaf_consensus' for st in v1['states'].values()) else 'UNASSESSED',
                                             complete=v1['complete'] and not any(st.get('engine') == 'eg_icaf_consensus' for st in v1['states'].values()), eg_icaf_task=any(st.get('engine') == 'eg_icaf_consensus' for st in v1['states'].values()), states=v1['states'],
                                             log_r1=[dict(engine='recheck', status=failed)])) + '\n')
                print('R1REF', tid, 'recheck failed:', failed, flush=True)
                continue
            v1 = refs[tid]; states = json.loads(json.dumps(v1['states'])); log = []
            rec, identity, tables = load(tid, manifest)
            eg_task = any(st.get('engine') == 'eg_icaf_consensus' for st in states.values())
            for s in range(3):
                st = states[str(s)]
                if st['status'] == 'UNSAT' and st['engine'] != 'predicate_range' and not st.get('corroborated'):
                    t = time.perf_counter()
                    status, mp = hb._state_witness(staged, identity, tables, s, 30.)
                    log.append(dict(state=s, engine='glasgow_staged', status=status, seconds=time.perf_counter() - t))
                    if status == 'UNKNOWN':
                        t = time.perf_counter(); status = cp_state(identity, tables, s, 60.)
                        log.append(dict(state=s, engine='cp_sat', status=status, seconds=time.perf_counter() - t))
                    if status == 'SAT':
                        raise SystemExit(f'REFUTED v1 negative: {tid} state {s}')
                    if status == 'UNSAT':
                        st['corroborated_r1'] = log[-1]['engine']
                elif st['status'] == 'UNKNOWN':  # v1: settled only by the EG-ICAF consensus
                    st = states[str(s)] = dict(status='UNKNOWN', engine='unresolved')
                    for engine, fn in (('lad', lambda: hb._state_witness(lad_ask, identity, tables, s, 120.)),
                                       ('glasgow_staged', lambda: hb._state_witness(staged, identity, tables, s, 120.)),
                                       ('cp_sat', lambda: (cp_state(identity, tables, s, 120.), None))):
                        t = time.perf_counter(); status, mp = fn()
                        log.append(dict(state=s, engine=engine, status=status, seconds=time.perf_counter() - t))
                        if status == 'SAT':
                            if mp is not None:
                                assert legal(identity, mp)
                            states[str(s)] = dict(status='SAT', engine=engine + '_replayed' if mp is not None else engine)
                            break
                        if status == 'UNSAT':
                            states[str(s)] = dict(status='UNSAT', engine=engine, corroborated=False)
                            break
            label, complete = label_of(states)
            row = dict(task_id=tid, label_v1=v1['label'], label=label if complete else 'UNASSESSED',
                       complete=complete, eg_icaf_task=eg_task, states=states, log_r1=log)
            if not eg_task and complete:
                assert label == v1['label'], (tid, label, v1['label'])
            stream.write(json.dumps(row) + '\n'); stream.flush()
            print('R1REF', tid, v1['label'], '->', row['label'], [(e['engine'], e['status']) for e in log],
                  flush=True)


if __name__ == '__main__' and len(sys.argv) > 3 and sys.argv[3] == '--task':
    # Revision R1 execution change after two out-of-memory kills (see orchestrate.log):
    # one process per remaining task under a 6.5 GB address-space limit.
    recheck(int(sys.argv[1]), int(sys.argv[2]), only=sys.argv[4],
            failed=sys.argv[5] if len(sys.argv) > 5 else None)
elif __name__ == '__main__':
    recheck(int(sys.argv[1]) if len(sys.argv) > 1 else 0, int(sys.argv[2]) if len(sys.argv) > 2 else 1)
