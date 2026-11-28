"""Revision R2 jobs (registered in results/revision_r2/design.json before any run).

Sub-commands
  generate    IdCon-Hard-X, IdCon-Hard-H and IdCon-Cite inputs (no solver call)
  pairs       (task, method) lists for the extended-budget runs, from records
  sample      the independent-check sample and the calibration sample
  overhead    per-component cost of the first LAD2025 / Glasgow --staged query
              on 48 IdCon-Hard tasks (Python preparation, file writing,
              solver process, solver-reported search time)
  orchestrate run every timed job, then the untimed ones (log: orchestrate.log)
Every job runs with an unlimited stack (LAD2025 crashes with the 8 MB default on
16,384-entity hosts) and PYTHONPATH=src (this machine sets PYTHONSAFEPATH).
"""
import collections
import json
import os
import random
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
OUT = ROOT / 'results/revision_r2'
PY = os.environ.get('IDCON_PY', sys.executable)
LOG = OUT / 'orchestrate.log'
SEEDS = dict(idcon_hard_x=202611280201, idcon_hard_h=202611280301, idcon_cite=202611280101,
             sample=202611280401)
HARDX_ENV = dict(IDCON_TIERS='16384:128', IDCON_DENSITY='1',
                 IDCON_SCENARIOS='decoy_v,decoy_u,focal_v,mixed,background,perturbed',
                 IDCON_COMBOS='forest:plain,induced:constrained')
CITE_METHODS = ['lad_state', 'glasgow', 'glasgow_staged', 'whole_cp', 'traditional_cp', 'first_match',
                'enum_glasgow', 'enum_nx', 'asp_cautious', 'sat_cadical']
HARDX_METHODS = ['lad_state', 'glasgow', 'glasgow_staged', 'whole_cp', 'enum_glasgow', 'first_match',
                 'sat_cadical']


def jl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def read(p):
    return json.loads(Path(p).read_text())


def records(suite, include=None, exclude=('b10', 'b60', 'r2calib')):
    rows = []
    for p in sorted((ROOT / 'results' / suite).glob('predictions*.jsonl')):
        name = p.name
        if include is not None:
            if not any(f'.{t}.' in name for t in include):
                continue
        elif any(f'.{t}.' in name for t in exclude):
            continue
        rows += jl(p)
    return rows


# ------------------------------------------------------------------ generate
def generate():
    env = {**os.environ, 'PYTHONPATH': str(SRC)}
    for study in ('idcon_hard_x', 'idcon_hard_h'):
        e = dict(env, IDCON_STUDY=study, IDCON_SEED=str(SEEDS[study]), **HARDX_ENV)
        subprocess.run([PY, 'hard_benchmark.py', 'generate'], cwd=SRC, env=e, check=True)
    subprocess.run([PY, 'external_cite.py'], cwd=SRC, env=dict(env, IDCON_STUDY='idcon_cite'), check=True)


# ------------------------------------------------------------------ pairs
def pairs():
    LEGACY = {'eg_icaf', 'lad_sv_early'}
    # IdCon-Hard 60 s: LAD / Glasgow-staged pairs unanswered at 10 s (repeat 0),
    # CP-SAT on every task that no method answered at 2 s or 10 s (repeat 0).
    two = [r for r in records('idcon_hard') if r['method'] not in LEGACY]
    ten = records('idcon_hard', include=['b10'])
    ref = {}
    for p in sorted((ROOT / 'data/protected/idcon_hard').glob('references_r1.w*.jsonl')):
        for r in jl(p):
            ref[r['task_id']] = r['label']
    ok = collections.defaultdict(bool)
    for r in two:
        if r['repeat'] == 0 and r['outcome'] == ref[r['task_id']]:
            ok[(r['task_id'], r['method'])] = True
    for r in ten:
        if r['outcome'] == ref[r['task_id']]:
            ok[(r['task_id'], r['method'])] = True
    tasks = sorted(ref)
    out = [(t, m) for t in tasks for m in ('lad_state', 'glasgow_staged') if not ok[(t, m)]]
    solved = {t for (t, m), v in ok.items() if v}
    out += [(t, 'whole_cp') for t in tasks if t not in solved]
    (OUT / 'pairs60.idcon_hard.json').write_text(json.dumps(out))
    print('PAIRS60 idcon_hard', len(out), collections.Counter(m for _, m in out))
    # IdCon-Hard-X 60 s: LAD / Glasgow-staged / SAT pairs unanswered at 10 s
    if (ROOT / 'results/idcon_hard_x').exists():
        rows = records('idcon_hard_x', include=['b10'])
        out = sorted({(r['task_id'], r['method']) for r in rows if r['outcome'] == 'NO_ANSWER'
                      and r['method'] in ('lad_state', 'glasgow_staged', 'sat_cadical')})
        (OUT / 'pairs60.idcon_hard_x.json').write_text(json.dumps(out))
        print('PAIRS60 idcon_hard_x', len(out))
    # IdCon-Cite 10 s: pairs unanswered in a 2 s repeat for five methods
    if (ROOT / 'results/idcon_cite').exists():
        rows = records('idcon_cite')
        out = sorted({(r['task_id'], r['method']) for r in rows if r['outcome'] == 'NO_ANSWER'
                      and r['method'] in ('lad_state', 'glasgow_staged', 'whole_cp', 'asp_cautious',
                                          'sat_cadical')})
        (OUT / 'pairs10.idcon_cite.json').write_text(json.dumps(out))
        print('PAIRS10 idcon_cite', len(out))


# ------------------------------------------------------------------ samples
def sample():
    rng = random.Random(SEEDS['sample'])
    hard = read(ROOT / 'data/processed/idcon_hard/manifest.json') + \
        read(ROOT / 'data/processed/idcon_hard/manifest_focal.json')
    by_id = {r['task_id']: r for r in hard}
    refs = {}
    for p in sorted((ROOT / 'data/protected/idcon_hard').glob('references_r1.w*.jsonl')):
        for r in jl(p):
            refs[r['task_id']] = r
    unconfirmed = sorted(t for t, r in refs.items() if any(
        s['status'] == 'UNSAT' and s['engine'] != 'predicate_range'
        and not (s.get('corroborated') or s.get('corroborated_r1')) for s in r['states'].values()))
    strata = collections.defaultdict(list)
    for t in sorted(by_id):
        if t not in unconfirmed:
            r = by_id[t]
            strata[(r['entities'], r['variant'])].append(t)
    picked = list(unconfirmed)
    for key in sorted(strata):
        picked += rng.sample(strata[key], 8)
    items = [dict(by_id[t], suite='idcon_hard',
                  why='unconfirmed_negative' if t in unconfirmed else 'stratified_random') for t in picked]
    xs = read(ROOT / 'data/processed/idcon_hprd_x/manifest.json')
    asp_ok = {r['task_id'] for r in records('idcon_hprd_x') if r['method'] == 'asp_cautious'
              and r['outcome'] != 'NO_ANSWER'}
    xrefs = {}
    for p in sorted((ROOT / 'data/protected/idcon_hprd_x').glob('references*.jsonl')):
        for r in jl(p):
            xrefs[r['task_id']] = r
    for r in xs:
        if r['task_id'] not in asp_ok:
            items.append(dict(r, suite='idcon_hprd_x', why='no_asp_answer'))
    (OUT / 'idcheck_sample.json').write_text(json.dumps(items))
    print('IDCHECK sample', len(items), collections.Counter(i['why'] for i in items), 'unconfirmed', len(unconfirmed))
    # calibration: 50 IdCon-Hard tasks x {LAD, Glasgow-staged}, repeat 0, 2 s
    tasks = rng.sample(sorted(by_id), 50)
    (OUT / 'pairs_calib.idcon_hard.json').write_text(json.dumps([(t, m) for t in tasks
                                                                 for m in ('lad_state', 'glasgow_staged')]))


# ------------------------------------------------------------------ overhead
def overhead():
    """Decompose the first two-query call (exists T in {S,U,V}) of LAD2025 and
    Glasgow --staged on 48 IdCon-Hard tasks (8 per tier x variant)."""
    import lad_baseline
    import glasgow_baseline
    rng = random.Random(SEEDS['sample'] + 1)
    hard = read(ROOT / 'data/processed/idcon_hard/manifest.json')
    strata = collections.defaultdict(list)
    for r in hard:
        strata[(r['entities'], r['variant'])].append(r)
    picked = [x for k in sorted(strata) for x in rng.sample(strata[k], 8)]
    rows = []
    for rec in picked:
        identity = read(ROOT / rec['identity_file'])
        for name, mod, extra in (('lad_state', lad_baseline, None), ('glasgow_staged', glasgow_baseline, ('--staged',))):
            captured = {}
            real = subprocess.run

            def spy(cmd, *a, **k):
                t = time.perf_counter()
                res = real(cmd, *a, **k)
                captured['solver_wall'] = time.perf_counter() - t
                captured['stdout'] = res.stdout
                return res
            mod.subprocess.run = spy
            t = time.perf_counter()
            try:
                if extra is None:
                    mod.ask(identity, {}, 0, {}, time.perf_counter() + 60)
                else:
                    mod.ask(identity, {}, 0, {}, time.perf_counter() + 60, glasgow_baseline.DEFAULT_BINARY, extra)
                status = 'ok'
            except Exception as exc:  # noqa: BLE001
                status = type(exc).__name__
            total = time.perf_counter() - t
            mod.subprocess.run = real
            internal = None
            so = captured.get('stdout') or ''
            m = re.search(r'runtime = (\d+)', so)
            if m:
                internal = int(m.group(1)) / 1000
            m = re.search(r'(\d+\.\d+) seconds', so)
            if internal is None and m:
                internal = float(m.group(1))
            rows.append(dict(task_id=rec['task_id'], entities=rec['entities'], variant=rec['variant'],
                             method=name, status=status, total_s=total,
                             solver_wall_s=captured.get('solver_wall'), solver_reported_s=internal))
    (OUT / 'overhead_hard.jsonl').write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    summary = {}
    for name in ('lad_state', 'glasgow_staged'):
        rs = [r for r in rows if r['method'] == name and r['solver_wall_s']]
        summary[name] = dict(calls=len(rs),
                             median_total_s=round(statistics.median(r['total_s'] for r in rs), 3),
                             median_solver_wall_s=round(statistics.median(r['solver_wall_s'] for r in rs), 3),
                             median_outside_solver_s=round(statistics.median(r['total_s'] - r['solver_wall_s'] for r in rs), 3),
                             median_solver_reported_s=(round(statistics.median(r['solver_reported_s'] for r in rs if r['solver_reported_s'] is not None), 3)
                                                       if any(r['solver_reported_s'] is not None for r in rs) else None))
    (OUT / 'overhead_hard.json').write_text(json.dumps(summary, indent=1))
    print('OVERHEAD', summary)


# ------------------------------------------------------------------ orchestrate
lock = threading.Lock()
heavy = threading.Lock()


def log(msg):
    with lock:
        with LOG.open('a') as f:
            f.write(time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ' ' + msg + '\n')


def infer(study, worker, workers, methods, tag=None, manifest=None, extra=None):
    env = dict(IDCON_STUDY=study)
    if tag:
        env['IDCON_PRED_TAG'] = tag
    if manifest:
        env['IDCON_MANIFEST'] = manifest
    env.update(extra or {})
    return env, [PY, 'hard_benchmark.py', 'infer', '--worker', str(worker), '--workers', str(workers),
                 '--methods', ','.join(methods)]


def job(name, env_cmd, is_heavy=False):
    env, cmd = env_cmd
    return (name, env, cmd, is_heavy)


def build_queue(phase):
    q = []
    X1 = dict(IDCON_REPEATS='1', **HARDX_ENV)
    if phase == 'timed':
        q.append(job('calib hard', infer('idcon_hard', 0, 1, ['lad_state', 'glasgow_staged'], 'r2calib', None,
                                         dict(IDCON_REPEATS='1', IDCON_PAIRS=str(OUT / 'pairs_calib.idcon_hard.json')))))
        q.append(job('calib hard_focal', infer('idcon_hard', 0, 1, ['lad_state', 'glasgow_staged'], 'r2calib',
                                               'manifest_focal.json',
                                               dict(IDCON_REPEATS='1', IDCON_PAIRS=str(OUT / 'pairs_calib.idcon_hard.json')))))
        for w in (0, 1):
            q.append(job(f'hardx 2s s{w}', infer('idcon_hard_x', w, 2, HARDX_METHODS, None, None, X1), True))
        for w in (0, 1):
            q.append(job(f'cite s{w}', infer('idcon_cite', w, 2, CITE_METHODS)))
        for w in (0, 1):
            q.append(job(f'hardx 10s s{w}', infer('idcon_hard_x', w, 2, HARDX_METHODS, 'b10', None,
                                                    dict(X1, IDCON_BUDGET='10')), True))
        for w in (0, 1):
            q += [job(f'sat hard s{w}', infer('idcon_hard', w, 2, ['sat_cadical'], 'r2')),
                  job(f'sat hard_focal s{w}', infer('idcon_hard', w, 2, ['sat_cadical'], 'r2', 'manifest_focal.json')),
                  job(f'sat hprd s{w}', infer('idcon_hprd', w, 2, ['sat_cadical'], 'r2')),
                  job(f'sat hprd_x s{w}', infer('idcon_hprd_x', w, 2, ['sat_cadical'], 'r2'))]
    elif phase == 'extended':
        P60 = dict(IDCON_BUDGET='60', IDCON_REPEATS='1')
        for w in (0, 1):
            q.append(job(f'B60 hard s{w}', infer('idcon_hard', w, 2, ['lad_state', 'glasgow_staged', 'whole_cp'], 'b60', None,
                                                 dict(P60, IDCON_PAIRS=str(OUT / 'pairs60.idcon_hard.json')))))
            q.append(job(f'B60 hard_focal s{w}', infer('idcon_hard', w, 2, ['lad_state', 'glasgow_staged', 'whole_cp'], 'b60',
                                                       'manifest_focal.json',
                                                       dict(P60, IDCON_PAIRS=str(OUT / 'pairs60.idcon_hard.json')))))
        for w in (0, 1):
            q.append(job(f'B60 hardx s{w}', infer('idcon_hard_x', w, 2, ['lad_state', 'glasgow_staged', 'sat_cadical'],
                                                  'b60', None, dict(X1, IDCON_BUDGET='60',
                                                                    IDCON_PAIRS=str(OUT / 'pairs60.idcon_hard_x.json'))), True))
            q.append(job(f'B10 cite s{w}', infer('idcon_cite', w, 2, ['lad_state', 'glasgow_staged', 'whole_cp',
                                                                      'asp_cautious', 'sat_cadical'], 'b10', None,
                                                 dict(IDCON_BUDGET='10', IDCON_REPEATS='1',
                                                      IDCON_PAIRS=str(OUT / 'pairs10.idcon_cite.json')))))
    elif phase == 'untimed':
        for study, extra in (('idcon_hard_x', HARDX_ENV), ('idcon_hard_h', HARDX_ENV), ('idcon_cite', {})):
            for w in (0, 1):
                q.append((f'reference {study} s{w}', dict(IDCON_STUDY=study, **extra),
                          [PY, 'hard_benchmark.py', 'reference', str(w), '2'], study != 'idcon_cite'))
        for w in (0, 1):
            q.append((f'idcheck s{w}', {}, [PY, str(SRC / 'r2_runs.py'), 'idcheck', str(w)], False))
    elif phase == 'last':
        q.append(('overhead', {}, [PY, str(SRC / 'r2_runs.py'), 'overhead'], False))
    return q


def run_queue(queue, cpus):
    def executor(cpu):
        while True:
            with lock:
                if not queue:
                    return
                # take the first job that can start now: a job on 16,384-entity
                # hosts waits while another such job runs (memory), but it does
                # not block this executor from taking a lighter job
                pick = None
                for i, item in enumerate(queue):
                    if not item[3] or heavy.acquire(blocking=False):
                        pick = queue.pop(i)
                        break
            if pick is None:
                time.sleep(5)
                continue
            name, env, cmd, is_heavy = pick
            log(f'START cpu{cpu} {name}')
            t = time.time()
            with (OUT / f'job_{name.replace(" ", "_")}.log').open('a') as out:
                full = {**os.environ, 'PYTHONPATH': str(SRC), **env}
                rc = subprocess.run(['taskset', '-c', str(cpu), 'bash', '-c', 'ulimit -s unlimited; exec "$@"', '_'] + cmd,
                                    cwd=SRC, env=full, stdout=out, stderr=subprocess.STDOUT).returncode
            log(f'END   cpu{cpu} {name} rc={rc} {time.time() - t:.0f}s')
            if is_heavy:
                heavy.release()
    threads = [threading.Thread(target=executor, args=(c,)) for c in cpus]
    [t.start() for t in threads]
    [t.join() for t in threads]


def idcheck(worker):
    """Independent check: the registered sample, then every IdCon-Cite and
    IdCon-Hard-X task (second engine for the new suites)."""
    a6 = OUT / 'amendment_6.json'
    if a6.exists():  # Amendment 6: order, Hard-X sample and limits (see the file)
        spec = read(a6)['idcheck']
        items = [dict(r, suite='idcon_cite', why='new_suite') for r in read(ROOT / 'data/processed/idcon_cite/manifest.json')]
        hx = read(ROOT / 'data/processed/idcon_hard_x/manifest.json')
        groups = collections.defaultdict(list)
        for r in hx:
            groups[r['group_id']].append(r)
        rng = random.Random(spec['hard_x_seed'])
        items += [dict(rng.choice(groups[g]), suite='idcon_hard_x', why='new_suite_sample') for g in sorted(groups)]
        items += read(OUT / 'idcheck_sample.json')
        if (OUT / 'amendment_7.json').exists():  # Amendment 7: every uncorroborated Hard-X negative
            refs = {}
            for p in sorted((ROOT / 'data/protected/idcon_hard_x').glob('references*.jsonl')):
                refs.update({r['task_id']: r for r in jl(p)})
            byid = {r['task_id']: r for r in hx}
            extra = sorted(t for t, r in refs.items() if r['complete'] and any(
                s['status'] == 'UNSAT' and s['engine'] != 'predicate_range' and not s.get('corroborated')
                for s in r['states'].values()))
            have = {r['task_id'] for r in items}
            items += [dict(byid[t], suite='idcon_hard_x', why='uncorroborated_negative') for t in extra if t not in have]
        done = set()
        for p in OUT.glob('idcheck.w*.jsonl'):
            done |= {r['task_id'] for r in jl(p)}
        (OUT / f'idcheck_part{worker}.json').write_text(json.dumps(items[worker::2]))
        mine = [r for r in items[worker::2] if r['task_id'] not in done]
        # memory: an item on a 16,384-entity host needs ~5 GB, so the runner may
        # split the work by suite (IDCON_IDCHECK_SUITES) and run those items alone
        only = os.environ.get('IDCON_IDCHECK_SUITES')
        skip = os.environ.get('IDCON_IDCHECK_SKIP_SUITES')
        if only:
            mine = [r for r in mine if r['suite'] in only.split(',')]
        if skip:
            mine = [r for r in mine if r['suite'] not in skip.split(',')]
        limits = [str(spec['solve_s']), str(spec['check_s'])]
        path = OUT / f'idcheck_todo{worker}.json'
        path.write_text(json.dumps(mine))
        subprocess.run([PY, str(ROOT / 'independent/idcheck.py'), 'run', str(path),
                        str(OUT / f'idcheck.w{worker}.jsonl')] + limits, check=True)
        return
    else:
        items = read(OUT / 'idcheck_sample.json')
        for study in ('idcon_cite', 'idcon_hard_x'):
            items += [dict(r, suite=study, why='new_suite') for r in read(ROOT / f'data/processed/{study}/manifest.json')]
        mine = items[worker::2]
        limits = ['600', '1200']
    path = OUT / f'idcheck_part{worker}.json'
    path.write_text(json.dumps(mine))
    subprocess.run([PY, str(ROOT / 'independent/idcheck.py'), 'run', str(path),
                    str(OUT / f'idcheck.w{worker}.jsonl')] + limits, check=True)


def orchestrate(phases):
    OUT.mkdir(parents=True, exist_ok=True)
    log('ORCHESTRATE begin ' + ','.join(phases))
    if os.environ.get('IDCON_SKIP_DONE_JOBS'):
        done = {m.group(1) for m in re.finditer(r'END\s+cpu\d+ (.*?) rc=0 ', LOG.read_text())}
        log('RESUME skipping finished jobs: ' + ', '.join(sorted(done)))
    for phase in phases:
        if phase == 'pairs':
            log('START pairs'); pairs(); log('END pairs')
            continue
        q = build_queue(phase)
        if os.environ.get('IDCON_SKIP_DONE_JOBS'):
            q = [j for j in q if j[0] not in done]
        run_queue(q, (0, 1) if phase != 'last' else (0,))
    log('ORCHESTRATE done ' + ','.join(phases))


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'generate':
        generate()
    elif cmd == 'pairs':
        pairs()
    elif cmd == 'sample':
        sample()
    elif cmd == 'overhead':
        overhead()
    elif cmd == 'idcheck':
        idcheck(int(sys.argv[2]))
    elif cmd == 'orchestrate':
        orchestrate(sys.argv[2].split(','))
