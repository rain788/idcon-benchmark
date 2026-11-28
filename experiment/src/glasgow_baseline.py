"""Same-semantics Glasgow subgraph baseline through a labelled graph reduction.

Role-specific domains and anchors become uniquely labelled pendant vertices.
Only length-constrained edges receive labelled pair vertices. Nonmetric edges
remain original graph edges. Every returned base mapping is replayed externally.
All graph construction, temporary-file I/O and solver process costs are timed.
"""
import math
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from projection_engine import Deadline, Unsupported, graph_data, guard
from full_benchmark_methods import rank_of

S,U,V=0,1,2
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_BINARY=ROOT/'third_party/build/glasgow_subgraph_solver'


def ask(identity, tables, base, restrictions, end, binary, extra=()):
    guard(end)
    g,q,anchors=graph_data(identity);n=len(g); xyz=np.asarray(identity['candidate_xyz'],dtype=float)
    if not set(anchors)<=set(q): raise Unsupported('anchor role outside query')
    domains={r: set(range(n)) for r in q}
    for r,u in anchors.items():domains[r]&={u}
    for _r,_v in {int(_r):set(_v) for _r,_v in identity.get('role_domains',{}).items()}.items():domains[_r]&=_v
    for r,permitted in restrictions.items():domains[r]&=set(permitted)
    if any(not d for d in domains.values()):return None
    pnodes=[f'p{r},,B' for r in q];tnodes=[f't{u},,B' for u in g]
    pedges=[f'p{r},p{s}' for r,s in q.edges]
    tedges=[f't{u},t{v}' for u,v in g.edges]
    # Separate labelled pendant forces each restricted role into its exact set.
    for r,domain in domains.items():
        guard(end)
        if len(domain)==n:continue
        pnodes.append(f'pr{r},,R{r}');pedges.append(f'p{r},pr{r}')
        for u in sorted(domain):
            tnodes.append(f'tr{r}_{u},,R{r}');tedges.append(f't{u},tr{r}_{u}')
    for k,(r,s,length,_) in enumerate(identity['role_edges']):
        if length is None:continue
        guard(end)
        pnodes.append(f'pe{k},,E{k}');pedges.extend((f'p{r},pe{k}',f'p{s},pe{k}'))
        for u,v in g.edges:
            guard(end)
            if abs(float(np.linalg.norm(xyz[u]-xyz[v]))-length)<identity['length_tolerance']:
                tnodes.append(f'te{k}_{u}_{v},,E{k}')
                tedges.extend((f't{u},te{k}_{u}_{v}',f't{v},te{k}_{u}_{v}'))
    guard(end)
    with tempfile.TemporaryDirectory(prefix='eg_glasgow_',dir='/dev/shm' if os.path.isdir('/dev/shm') else None) as tmp:
        pattern=Path(tmp)/'pattern.csv';target=Path(tmp)/'target.csv'
        pattern.write_text('\n'.join(pnodes+pedges)+'\n',encoding='ascii')
        target.write_text('\n'.join(tnodes+tedges)+'\n',encoding='ascii')
        guard(end)
        try:
            completed=subprocess.run([str(binary),*extra,'--format','csv',str(pattern),str(target)],capture_output=True,
                     text=True,timeout=max(0.0001,end-time.perf_counter()),check=False)
        except subprocess.TimeoutExpired:
            raise Deadline()
        guard(end)
        if completed.returncode:raise RuntimeError('Glasgow failure: '+completed.stderr[-1500:]+completed.stdout[-1500:])
        status=re.search(r'^status = (true|false|aborted)\s*$',completed.stdout,re.M)
        if not status:raise RuntimeError('Glasgow returned unrecognized status: '+completed.stdout[-1500:])
        if status.group(1)=='aborted':raise Deadline()
        if status.group(1)=='false':return None
        mappingline=re.search(r'^mapping = (.*)$',completed.stdout,re.M)
        if not mappingline:raise RuntimeError('Glasgow missing mapping')
        maps={int(r):int(u) for r,u in re.findall(r'\(p(\d+) -> t(\d+)\)',mappingline.group(1))}
        if set(maps)!=set(q):raise RuntimeError('Glasgow mapping misses base roles')
        mapping=[maps[r] for r in range(len(q))]
        return {'mapping':mapping,'state':rank_of(mapping,tables,base)}


def diagnose_tables(identity,tables,base=S,timeout=1.,binary=DEFAULT_BINARY,extra=()):
    start=time.perf_counter();end=start+timeout;calls=0;mappings=[]
    try:
        def query(restrictions):
            nonlocal calls
            calls+=1;return ask(identity,tables,base,restrictions,end,binary,extra)
        first=query({})
        if first is None:result=dict(label='UNKNOWN',reason='identity_inconsistent',certificate=True)
        else:
            mappings.append(first['mapping']);state=first['state']
            if state==U:result=dict(label='UNKNOWN',reason='missing_evidence_witness',certificate=True)
            else:
                if state==V:
                    other=None if base==V else query({r:[u for u,x in enumerate(values) if x<V] for r,values in tables.items()})
                else:
                    other=None
                    for r,values in sorted(tables.items()):
                        guard(end)
                        possible=[u for u,x in enumerate(values) if x>S]
                        if possible:
                            other=query({r:possible})
                            if other is not None:break
                if other is None:
                    result=dict(label=['SATISFIES','UNKNOWN','VIOLATES'][state],reason='counterexample_excluded',certificate=True)
                else:
                    mappings.append(other['mapping']);result=dict(label='UNKNOWN',reason='conflicting_identity_witnesses',certificate=True)
        guard(end)
    except Deadline:
        result=dict(label='UNKNOWN',reason='budget',certificate=False)
    except Unsupported as exc:
        result=dict(label='UNKNOWN',reason='identity_binding_unsupported',certificate=False,detail=str(exc))
    elapsed=time.perf_counter()-start
    result.update(route='glasgow_gadget',seconds=elapsed,mappings=mappings,solver_calls=calls)
    if elapsed>timeout:result.update(label='UNKNOWN',reason='deadline_overrun',certificate=False)
    return result
