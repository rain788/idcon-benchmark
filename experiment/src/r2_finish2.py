"""Revision R2: reruns after the second round of OOM kills (orchestrate.log, 14:33)."""
import r2_runs as r

q = [j for j in r.build_queue('untimed') if j[0] == 'reference idcon_hard_h s1']
q.append(('idcheck-HardX s0', {'IDCON_IDCHECK_SUITES': 'idcon_hard_x'},
          [r.PY, str(r.SRC / 'r2_runs.py'), 'idcheck', '0'], True))
r.log('FINISH2 begin ' + ', '.join(j[0] for j in q))
r.run_queue(q, (0,))
r.log('FINISH2 done')
