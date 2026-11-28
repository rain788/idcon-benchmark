"""Run the registered R1 jobs on the 2-vCPU VM: two single-thread executors,
each pinned to one vCPU (taskset), pulling jobs in order; B10 starts only after
every 2 s job on idcon_hard / idcon_hprd has finished; the overhead measurement
runs last, alone. Log: results/revision_r1/orchestrate.log
"""
import os, subprocess, sys, threading, time
from pathlib import Path
SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
PY = os.environ.get('IDCON_PY', sys.executable)
LOG = ROOT / 'results/revision_r1/orchestrate.log'
NEW = 'enum_glasgow,enum_nx,asp_cautious'
ALL = 'lad_state,glasgow,glasgow_staged,whole_cp,traditional_cp,first_match,' + NEW


def infer(study, worker, methods, tag=None, manifest=None, extra=None):
    env = dict(IDCON_STUDY=study)
    if tag: env['IDCON_PRED_TAG'] = tag
    if manifest: env['IDCON_MANIFEST'] = manifest
    env.update(extra or {})
    return (env, [PY, 'hard_benchmark.py', 'infer', '--worker', str(worker), '--workers', '2', '--methods', methods])


PHASE1 = []
for w in (0, 1):
    PHASE1 += [(f'R1_main hard s{w}', *infer('idcon_hard', w, NEW, 'r1')),
               (f'R1_main hard_focal s{w}', *infer('idcon_hard', w, NEW, 'r1', 'manifest_focal.json')),
               (f'R1_main hprd s{w}', *infer('idcon_hprd', w, NEW, 'r1'))]
PHASE1 += [('recheck hard s0', dict(IDCON_STUDY='idcon_hard'), [PY, 'revision_references.py', '0', '2']),
           ('recheck hard s1', dict(IDCON_STUDY='idcon_hard'), [PY, 'revision_references.py', '1', '2'])]
for w in (0, 1):
    PHASE1 += [(f'R1_X s{w}', *infer('idcon_hprd_x', w, ALL))]
for w in (0, 1):
    PHASE1 += [(f'reference hprd_x s{w}', dict(IDCON_STUDY='idcon_hprd_x'), [PY, 'hard_benchmark.py', 'reference', str(w), '2']),
               (f'reference hprd_h s{w}', dict(IDCON_STUDY='idcon_hprd_h'), [PY, 'hard_benchmark.py', 'reference', str(w), '2'])]
PHASE1 += [('counts', {}, [PY, 'revision_counts.py'])]
B10 = dict(IDCON_BUDGET='10', IDCON_REPEATS='1')
PHASE2 = [('pairs10', {}, [PY, 'revision_runs.py', 'pairs10'])]
PHASE3 = []
for w in (0, 1):
    PHASE3 += [(f'B10 hard s{w}', *infer('idcon_hard', w, 'lad_state,glasgow_staged,whole_cp,enum_glasgow', 'b10', None,
                                         dict(B10, IDCON_PAIRS=str(ROOT / 'results/revision_r1/pairs10.idcon_hard.json')))),
               (f'B10 hard_focal s{w}', *infer('idcon_hard', w, 'lad_state,glasgow_staged,whole_cp,enum_glasgow', 'b10', 'manifest_focal.json',
                                               dict(B10, IDCON_PAIRS=str(ROOT / 'results/revision_r1/pairs10.idcon_hard.json')))),
               (f'B10 hprd s{w}', *infer('idcon_hprd', w, 'lad_state,glasgow_staged,whole_cp,enum_glasgow,glasgow', 'b10', None,
                                         dict(B10, IDCON_PAIRS=str(ROOT / 'results/revision_r1/pairs10.idcon_hprd.json'))))]
PHASE4 = [('overhead', {}, [PY, 'revision_runs.py', 'overhead'])]

lock = threading.Lock()


def log(msg):
    with lock:
        with LOG.open('a') as f:
            f.write(time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ' ' + msg + '\n')


def run_queue(queue, cpus):
    def executor(cpu):
        while True:
            with lock:
                if not queue:
                    return
                name, env, cmd = queue.pop(0)
            log(f'START cpu{cpu} {name}')
            t = time.time()
            with (ROOT / 'results/revision_r1' / f'job_{name.replace(" ", "_")}.log').open('a') as out:
                rc = subprocess.run(['taskset', '-c', str(cpu)] + cmd, cwd=SRC, env={**os.environ, **env},
                                    stdout=out, stderr=subprocess.STDOUT).returncode
            log(f'END   cpu{cpu} {name} rc={rc} {time.time() - t:.0f}s')
    threads = [threading.Thread(target=executor, args=(c,)) for c in cpus]
    [t.start() for t in threads]; [t.join() for t in threads]


RECHECK = [('recheck hard serial', dict(IDCON_STUDY='idcon_hard'), [PY, 'revision_references.py', '0', '2']),
           ('recheck hard serial', dict(IDCON_STUDY='idcon_hard'), [PY, 'revision_references.py', '1', '2'])]

if __name__ == '__main__' and sys.argv[1:] == ['resume']:
    # The VM restarted at about 20:30 UTC during 'counts'; the two concurrent
    # re-check shards had been killed by the out-of-memory killer (each CP-SAT /
    # Glasgow query on 8,192-entity hosts needs about 3 GB). Resume: finish the
    # counts, run phases 2-4, then the re-check alone, one shard after the other.
    log('ORCHESTRATE resume')
    run_queue([j for j in PHASE1 if j[0] == 'counts'], (0,))
    run_queue(list(PHASE2), (0,))
    run_queue(list(PHASE3), (0, 1))
    run_queue(list(PHASE4), (0,))
    run_queue(list(RECHECK), (0,))
    log('ORCHESTRATE done')
elif __name__ == '__main__':
    log('ORCHESTRATE begin')
    run_queue(list(PHASE1), (0, 1))
    run_queue(list(PHASE2), (0,))
    run_queue(list(PHASE3), (0, 1))
    run_queue(list(PHASE4), (0,))
    log('ORCHESTRATE done')
