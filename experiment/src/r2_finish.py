"""Revision R2: the jobs that the orchestrator could not finish (see the DEVIATION
lines of results/revision_r2/orchestrate.log), each alone on cpu0 because each
needs most of the machine's 8 GB: the IdCon-Hard-H reference shard 1 (resumed
from its records), the IdCon-Hard-X items of the independent check (Amendment 6),
and the 60 s IdCon-Hard-X reruns (resumed from their records). Same commands and
environments as in r2_runs.build_queue."""
import r2_runs as r

q = [j for j in r.build_queue('untimed') if j[0] == 'reference idcon_hard_h s1']
for w in (0, 1):
    q.append((f'idcheck-HardX s{w}', {'IDCON_IDCHECK_SUITES': 'idcon_hard_x'},
              [r.PY, str(r.SRC / 'r2_runs.py'), 'idcheck', str(w)], True))
q += [j for j in r.build_queue('extended') if j[0].startswith('B60 hardx')]
r.log('FINISH begin ' + ', '.join(j[0] for j in q))
r.run_queue(q, (0,))
r.log('FINISH done')
