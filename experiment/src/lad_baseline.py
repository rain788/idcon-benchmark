"""Equal-semantics LAD2025 comparator. Never imported by the public method.

Fixed universal roots preserve all original identities while avoiding the
native isolated-vertex shortcut. Arbitrary role domains and metrics are passed
to documented hooks before native filtering, not checked only after stopping.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

import numpy as np

from projection_engine import graph_data,guard,Deadline
from full_benchmark_methods import rank_of

ROOT=Path(__file__).resolve().parents[1]
BINARY=ROOT/'third_party/build/lad2025/lad2025'


def write_graph(path,g):
    path.write_text('\n'.join([str(len(g))]+[
        ' '.join(map(str,[g.degree[u],*sorted(g[u])])) for u in range(len(g))])+'\n')


def ask(identity,tables,base,restrictions,end,binary=BINARY):
    guard(end);g,q,a=graph_data(identity);n=len(g);m=len(q)
    if m>n:return None
    domains=[{a[r]} if r in a else set(g)-set(a.values()) for r in q]
    for _r,_v in {int(_r):set(_v) for _r,_v in identity.get('role_domains',{}).items()}.items():domains[_r]&=_v
    for r,values in restrictions.items():domains[r]&=set(values)
    if any(not d for d in domains):return None
    metrics=[];xyz=np.asarray(identity['candidate_xyz'])
    for r,s,length,_ in identity['role_edges']:
        if length is not None:
            guard(end)
            allowed=[(u,v) for u,v in g.edges if abs(float(np.linalg.norm(xyz[u]-xyz[v]))-length)<identity['length_tolerance']]
            metrics.append((r,s,allowed))
    # The new target root is excluded from every original role domain.
    # Its fixed pattern image preserves precisely the original non-induced maps.
    g=g.copy();q=q.copy()
    g.add_node(n);q.add_node(m)
    g.add_edges_from((n,u) for u in range(n));q.add_edges_from((m,r) for r in range(m))
    domains.append({n})
    lines=[f'{m+1} {n+1}',*[' '.join(map(str,[len(d),*sorted(d)])) for d in domains],str(len(metrics))]
    for r,s,allowed in metrics:
        lines.append(f'{r} {s} {len(allowed)}')
        lines.extend(f'{u} {v}' for u,v in allowed)
    guard(end)
    with tempfile.TemporaryDirectory(prefix='eg_lad_',dir='/dev/shm' if os.path.isdir('/dev/shm') else None) as tmp:
        p=Path(tmp);write_graph(p/'q',q);write_graph(p/'g',g)
        (p/'constraints').write_text('\n'.join(lines)+'\n')
        env=os.environ.copy();env['EG_LAD_CONSTRAINTS']=str(p/'constraints')
        guard(end)
        try:
            process=subprocess.run([str(binary),'-p',str(p/'q'),'-t',str(p/'g'),'-v','-s','3600'],
                capture_output=True,text=True,env=env,timeout=max(.0001,end-time.perf_counter()))
        except subprocess.TimeoutExpired:raise Deadline()
        guard(end)
        if process.returncode:raise RuntimeError('LAD2025 failure: '+process.stdout[-1000:]+process.stderr[-1000:])
        if 'Time exceeded' in process.stdout:raise Deadline()
        status=re.search(r'Run completed: (\d+) solutions;',process.stdout)
        if not status:raise RuntimeError('LAD2025 missing completion status: '+process.stdout[-1000:])
        if int(status[1])==0:return None
        solution=re.search(r'^Solution 1: (.*)$',process.stdout,re.M)
        if not solution:raise RuntimeError('LAD2025 missing witness')
        found={int(r):int(u) for r,u in re.findall(r'(\d+)=(\d+)',solution[1])}
        if set(found)!=set(range(m+1)) or found[m]!=n:raise RuntimeError('LAD2025 incomplete/root-invalid mapping')
        mapping=[found[r] for r in range(m)]
        return dict(mapping=mapping,state=rank_of(mapping,tables,base))


def diagnose_tables(identity,tables,base=0,timeout=2.,binary=BINARY):
    start=time.perf_counter();end=start+timeout;calls=0;mappings=[]
    try:
        def query(restrictions):
            nonlocal calls
            calls+=1
            return ask(identity,tables,base,restrictions,end,binary)
        first=query({})
        if first is None:result=dict(label='UNKNOWN',reason='identity_inconsistent',certificate=True)
        else:
            mappings.append(first['mapping']);state=first['state'];other=None
            if state==1:result=dict(label='UNKNOWN',reason='missing_evidence_witness',certificate=True)
            else:
                if state==2:
                    if base<2:other=query({r:[u for u,x in enumerate(v) if x<2] for r,v in tables.items()})
                else:
                    for r,values in sorted(tables.items()):
                        possible=[u for u,x in enumerate(values) if x>0]
                        if possible:
                            other=query({r:possible})
                            if other is not None:break
                if other is not None:
                    mappings.append(other['mapping']);result=dict(label='UNKNOWN',reason='conflicting_identity_witnesses',certificate=True)
                else:result=dict(label=['SATISFIES','UNKNOWN','VIOLATES'][state],reason='counterexample_excluded',certificate=True)
        guard(end)
    except Deadline:
        result=dict(label='UNKNOWN',reason='budget',certificate=False)
    elapsed=time.perf_counter()-start
    if elapsed>timeout:result.update(label='UNKNOWN',reason='deadline_overrun',certificate=False)
    return dict(**result,seconds=elapsed,mappings=mappings,solver_calls=calls,route='lad2025_domain_adapter')
