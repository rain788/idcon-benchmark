"""Revision R2: worker 1 of the independent check again, for the items Amendment 7 added."""
import r2_runs as r

q = [('idcheck-HardX-A7 s1', {'IDCON_IDCHECK_SUITES': 'idcon_hard_x'},
      [r.PY, str(r.SRC / 'r2_runs.py'), 'idcheck', '1'], True)]
r.log('FINISH3 begin ' + ', '.join(j[0] for j in q))
r.run_queue(q, (0,))
r.log('FINISH3 done')
