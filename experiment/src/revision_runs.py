"""Revision R1 run helpers.

pairs10   write the (task, method) list for the 10 s extended-budget run (R1_B10):
          every pair that returned NO_ANSWER in at least one 2 s repeat.
overhead  fixed per-call cost on IdCon-HPRD (R1_overhead): writing the host
          graph, and one LAD2025 / Glasgow / Glasgow --staged call on a one-role
          pattern; 20 calls each, on the first IdCon-HPRD identity.
"""
import json, os, statistics, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/revision_r1'
B10_METHODS = {'idcon_hard': ['lad_state', 'glasgow_staged', 'whole_cp', 'enum_glasgow'],
               'idcon_hprd': ['lad_state', 'glasgow_staged', 'whole_cp', 'enum_glasgow', 'glasgow']}


def jl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def pairs10():
    for suite, methods in B10_METHODS.items():
        res = ROOT / 'results' / suite
        rows = []
        for p in sorted(res.glob('predictions*.jsonl')):
            rows += jl(p)
        na = sorted({(r['task_id'], r['method']) for r in rows
                     if r['method'] in methods and r['outcome'] == 'NO_ANSWER'})
        (OUT / f'pairs10.{suite}.json').write_text(json.dumps(na))
        print('PAIRS10', suite, len(na), {m: sum(1 for _, x in na if x == m) for m in methods})


def overhead():
    from lad_baseline import ask as lad_ask, write_graph
    from glasgow_baseline import ask as gl_ask, DEFAULT_BINARY
    from projection_engine import graph_data
    data = ROOT / 'data/processed/idcon_hprd'
    first = json.loads((data / 'manifest.json').read_text())[0]
    identity = json.loads((ROOT / first['identity_file']).read_text())
    one = dict(identity, role_count=1, role_edges=[], role_domains={})
    rows = []
    g, q, a = graph_data(identity)
    for i in range(20):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as tmp:
            t = time.perf_counter(); write_graph(Path(tmp) / 'g', g); rows.append(('write_host_graph', time.perf_counter() - t))
        for name, fn in (('lad_one_role', lambda: lad_ask(one, {}, 0, {}, time.perf_counter() + 30)),
                         ('glasgow_one_role', lambda: gl_ask(one, {}, 0, {}, time.perf_counter() + 30, DEFAULT_BINARY)),
                         ('glasgow_staged_one_role', lambda: gl_ask(one, {}, 0, {}, time.perf_counter() + 30, DEFAULT_BINARY, ('--staged',))),
                         ('graph_data', lambda: graph_data(identity))):
            t = time.perf_counter(); fn(); rows.append((name, time.perf_counter() - t))
    summary = {k: dict(median_ms=round(1000 * statistics.median(v for n, v in rows if n == k), 1),
                       min_ms=round(1000 * min(v for n, v in rows if n == k), 1))
               for k in dict.fromkeys(n for n, _ in rows)}
    (OUT / 'overhead.json').write_text(json.dumps(dict(identity=first['task_id'], calls=20, summary=summary), indent=1))
    print('OVERHEAD', summary)


if __name__ == '__main__':
    {'pairs10': pairs10, 'overhead': overhead}[sys.argv[1]]()
