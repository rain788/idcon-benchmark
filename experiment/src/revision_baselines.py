"""Revision R1 baselines: tools that are not written by the benchmark authors.

enum_glasgow  enumerate every admissible identity with the Glasgow Subgraph
              Solver (--print-all-solutions, same labelled-gadget encoding as
              glasgow_baseline.py) and aggregate the observed states.
enum_nx       enumerate every admissible identity with NetworkX VF2
              (GraphMatcher.subgraph_monomorphisms_iter) and aggregate.
asp_cautious  certain-answer reasoning with clingo: the identity space is an
              answer-set program and the consensus is the set of cautious
              consequences over the aggregate state atom t/1.

All three share one rule for early termination: as soon as two identities
with different states, or one identity with state U, have been seen, the answer
UNKNOWN is certified by the two (or one) replayable witnesses. SATISFIES,
VIOLATES and EMPTY are certified only by a completed enumeration (or, for
ASP, by clingo's completed cautious-consequence computation).

Budgets are enforced as hard wall-clock limits: Glasgow runs as a child
process that is killed at the deadline; VF2 is interrupted by SIGALRM; clingo
grounding and solving run in a forked child process that is killed at the
deadline. All set-up, encoding and process costs are inside the timed call.
"""
import multiprocessing as mp
import os
import re
import select
import signal
import subprocess
import tempfile
import time
from pathlib import Path

import networkx as nx
import numpy as np

from projection_engine import Deadline, Unsupported, graph_data
from full_benchmark_methods import rank_of

S, U, V = 0, 1, 2
ROOT = Path(__file__).resolve().parents[1]
GLASGOW = Path(os.environ.get('IDCON_GLASGOW', ROOT / 'third_party/build/glasgow_subgraph_solver'))
LABEL = ['SATISFIES', 'UNKNOWN', 'VIOLATES']


def domains_of(identity, g, q, anchors):
    """Role domains implied by anchors and unary domains (no restrictions)."""
    used = set(anchors.values())
    dom = {r: ({anchors[r]} if r in anchors else set(g) - used) for r in q}
    for r, values in identity.get('role_domains', {}).items():
        dom[int(r)] &= set(values)
    return dom


def metric_pairs(identity, g):
    xyz = np.asarray(identity['candidate_xyz'], dtype=float)
    out = {}
    for k, (r, s, length, _) in enumerate(identity['role_edges']):
        if length is None:
            continue
        out[k] = (r, s, {(u, v) for u, v in g.edges
                         if abs(float(np.linalg.norm(xyz[u] - xyz[v])) - length) < identity['length_tolerance']})
    return out


class Aggregator:
    """Collect states of enumerated identities; decide when UNKNOWN is certain."""

    def __init__(self, tables, base):
        self.tables, self.base = tables, base
        self.seen = {}  # state -> first witness
        self.count = 0

    def add(self, mapping):
        self.count += 1
        state = rank_of(mapping, self.tables, self.base)
        self.seen.setdefault(state, list(mapping))
        return U in self.seen or (S in self.seen and V in self.seen)

    def result(self, complete):
        if U in self.seen:
            return dict(label='UNKNOWN', reason='missing_evidence_witness', certificate=True,
                        mappings=[self.seen[U]])
        if S in self.seen and V in self.seen:
            return dict(label='UNKNOWN', reason='conflicting_identity_witnesses', certificate=True,
                        mappings=[self.seen[S], self.seen[V]])
        if not complete:
            return dict(label='UNKNOWN', reason='budget', certificate=False,
                        mappings=list(self.seen.values()))
        if not self.seen:
            return dict(label='UNKNOWN', reason='identity_inconsistent', certificate=True, mappings=[])
        state = next(iter(self.seen))
        return dict(label=LABEL[state], reason='enumeration_complete', certificate=True,
                    mappings=[self.seen[state]])


def _finish(result, start, budget, route, **extra):
    elapsed = time.perf_counter() - start
    result.update(seconds=elapsed, route=route, **extra)
    if elapsed > budget:
        result.update(label='UNKNOWN', reason='deadline_overrun', certificate=False)
    return result


# ------------------------------------------------------------ Glasgow enumeration
MAPPING = re.compile(r'\(p(\d+) -> t(\d+)\)')


def enum_glasgow(identity, tables, base=S, budget=2.0, binary=None):
    start = time.perf_counter(); end = start + budget
    agg = Aggregator(tables, base); complete = False; proc = None
    binary = Path(binary or GLASGOW)
    try:
        g, q, anchors = graph_data(identity)
        dom = domains_of(identity, g, q, anchors)
        if any(not d for d in dom.values()):
            complete = True
            return _finish(agg.result(True), start, budget, 'enum_glasgow', solutions=0)
        n = len(g)
        pnodes = [f'p{r},,B' for r in q]; tnodes = [f't{u},,B' for u in g]
        pedges = [f'p{r},p{s}' for r, s in q.edges]; tedges = [f't{u},t{v}' for u, v in g.edges]
        for r, d in dom.items():
            if len(d) == n:
                continue
            pnodes.append(f'pr{r},,R{r}'); pedges.append(f'p{r},pr{r}')
            for u in sorted(d):
                tnodes.append(f'tr{r}_{u},,R{r}'); tedges.append(f't{u},tr{r}_{u}')
        for k, (r, s, allowed) in metric_pairs(identity, g).items():
            pnodes.append(f'pe{k},,E{k}'); pedges.extend((f'p{r},pe{k}', f'p{s},pe{k}'))
            for u, v in sorted(allowed):
                tnodes.append(f'te{k}_{u}_{v},,E{k}'); tedges.extend((f't{u},te{k}_{u}_{v}', f't{v},te{k}_{u}_{v}'))
            if time.perf_counter() >= end:
                raise Deadline()
        with tempfile.TemporaryDirectory(prefix='idcon_enum_', dir='/dev/shm' if os.path.isdir('/dev/shm') else None) as tmp:
            pattern = Path(tmp) / 'pattern.csv'; target = Path(tmp) / 'target.csv'
            pattern.write_text('\n'.join(pnodes + pedges) + '\n', encoding='ascii')
            target.write_text('\n'.join(tnodes + tedges) + '\n', encoding='ascii')
            proc = subprocess.Popen(['stdbuf', '-oL', str(binary), '--print-all-solutions', '--format', 'csv',
                                     str(pattern), str(target)], stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, bufsize=1)
            status = None; buffer = ''
            fd = proc.stdout.fileno()
            while True:
                remaining = end - time.perf_counter()
                if remaining <= 0:
                    raise Deadline()
                ready, _, _ = select.select([fd], [], [], remaining)
                if not ready:
                    raise Deadline()
                chunk = os.read(fd, 1 << 16).decode('ascii', 'replace')
                if not chunk:
                    break
                buffer += chunk
                *lines, buffer = buffer.split('\n')
                stop = False
                for line in lines:
                    if line.startswith('mapping = '):
                        found = {int(r): int(u) for r, u in MAPPING.findall(line)}
                        mapping = [found[r] for r in range(len(q))]
                        if agg.add(mapping):
                            stop = True; break
                    elif line.startswith('status = '):
                        status = line.split('=', 1)[1].strip()
                if stop:
                    break
            if not agg.result(False)['certificate']:
                proc.wait(timeout=max(1e-3, end - time.perf_counter()))
                if status is None and buffer.startswith('status = '):
                    status = buffer.split('=', 1)[1].strip()
                if proc.returncode:
                    raise RuntimeError(f'Glasgow exited with code {proc.returncode}')
                if status not in ('true', 'false'):
                    raise Deadline()
                complete = True
        result = agg.result(complete)
    except (Deadline, subprocess.TimeoutExpired):
        result = agg.result(False)
    except Unsupported as exc:
        result = dict(label='UNKNOWN', reason='identity_binding_unsupported', certificate=False,
                      mappings=[], detail=str(exc))
    except RuntimeError as exc:
        result = dict(label='UNKNOWN', reason='runtime_error', certificate=False,
                      mappings=[], detail=str(exc)[:300])
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill(); proc.wait()
    return _finish(result, start, budget, 'enum_glasgow', solutions=agg.count)


# ------------------------------------------------------------ NetworkX VF2 enumeration
def _alarm(signum, frame):
    raise Deadline()


def enum_nx(identity, tables, base=S, budget=2.0):
    start = time.perf_counter(); end = start + budget
    agg = Aggregator(tables, base); complete = False
    previous = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, budget)
    try:
        g, q, anchors = graph_data(identity)
        dom = domains_of(identity, g, q, anchors)
        if any(not d for d in dom.values()):
            complete = True
        else:
            n = len(g)
            for u in g:
                g.nodes[u]['id'] = u
            for r in q:
                q.nodes[r]['dom'] = None if len(dom[r]) == n else dom[r]
            metric = metric_pairs(identity, g)
            for k, (r, s, allowed) in metric.items():
                q.edges[r, s]['ok'] = allowed
            def node_match(gn, qn):
                return qn['dom'] is None or gn['id'] in qn['dom']
            matcher = nx.algorithms.isomorphism.GraphMatcher(g, q, node_match=node_match)
            for gmap in matcher.subgraph_monomorphisms_iter():
                inv = {r: u for u, r in gmap.items()}
                ok = True
                for k, (r, s, allowed) in metric.items():
                    a, b = inv[r], inv[s]
                    if (a, b) not in allowed and (b, a) not in allowed:
                        ok = False; break
                if not ok:
                    continue
                if agg.add([inv[r] for r in range(len(q))]):
                    break
            else:
                complete = True
        result = agg.result(complete)
    except Deadline:
        result = agg.result(False)
    except Unsupported as exc:
        result = dict(label='UNKNOWN', reason='identity_binding_unsupported', certificate=False,
                      mappings=[], detail=str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    return _finish(result, start, budget, 'enum_nx', solutions=agg.count)


# ------------------------------------------------------------ ASP cautious reasoning
ASP_PROGRAM = """
1 { map(R,N) : cand(R,N) } 1 :- role(R).
:- map(R1,N), map(R2,N), R1 < R2.
nb(S,N) :- map(S,M), gedge(M,N), qedge(_,S).
:- qedge(R,S), map(R,N), not nb(S,N).
:- medge(K,R,S), map(R,N), map(S,M), not mok(K,N,M).
high(X) :- map(R,N), val(R,N,X).
high(X) :- base(X), X > 0.
t(2) :- high(2).
t(1) :- high(1), not high(2).
t(0) :- not high(1), not high(2).
#show t/1.
#show map/2.
"""


def _asp_facts(identity, tables, base):
    g, q, anchors = graph_data(identity)
    dom = domains_of(identity, g, q, anchors)
    if any(not d for d in dom.values()):
        return None
    out = [f'base({base}).']
    out += [f'role({r}).' for r in q]
    for r, d in dom.items():
        need = q.degree[r]
        out += [f'cand({r},{u}).' for u in sorted(d) if g.degree[u] >= need]
    for u, v in g.edges:
        out.append(f'gedge({u},{v}). gedge({v},{u}).')
    metric = metric_pairs(identity, g)
    for r, s, length, _ in identity['role_edges']:
        out.append(f'qedge({r},{s}). qedge({s},{r}).')
    for k, (r, s, allowed) in metric.items():
        out.append(f'medge({k},{r},{s}).')
        out += [f'mok({k},{u},{v}). mok({k},{v},{u}).' for u, v in sorted(allowed)]
    for r, values in tables.items():
        out += [f'val({r},{u},{x}).' for u, x in enumerate(values) if x > 0]
    return '\n'.join(out), len(q)


def _asp_child(conn, identity, tables, base):
    import clingo
    facts = _asp_facts(identity, tables, base)
    if facts is None:
        conn.send(('done', [], [], True)); return
    text, k = facts
    ctl = clingo.Control(['--enum-mode=cautious', '--models=0', '--warn=none'])
    ctl.add('base', [], ASP_PROGRAM + text)
    ctl.ground([('base', [])])
    witnesses = []; cautious = None
    with ctl.solve(yield_=True) as handle:
        for model in handle:
            # In cautious mode each reported model carries the current
            # intersection of all models found so far (shown atoms only).
            atoms = model.symbols(shown=True)
            ts = {a.arguments[0].number for a in atoms if a.name == 't'}
            mp_ = {a.arguments[0].number: a.arguments[1].number for a in atoms if a.name == 'map'}
            if len(mp_) == k and not witnesses:
                witnesses.append([mp_[r] for r in range(k)])
            cautious = ts
            if not ts or 1 in ts:
                # Two models disagree on t/1, or some model has state U:
                # UNKNOWN is certain; stop without exhausting the search.
                conn.send(('done', sorted(ts), witnesses, True))
                return
        result = handle.get()
    conn.send(('done', sorted(cautious) if cautious is not None else None, witnesses,
               bool(result.exhausted)))


def asp_cautious(identity, tables, base=S, budget=2.0):
    start = time.perf_counter(); end = start + budget
    ctx = mp.get_context('fork')
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_asp_child, args=(child, identity, tables, base), daemon=True)
    proc.start(); child.close()
    last = None
    try:
        while True:
            remaining = end - time.perf_counter()
            if remaining <= 0 or not parent.poll(remaining):
                raise Deadline()
            try:
                msg = parent.recv()
            except EOFError:
                raise RuntimeError('clingo child ended without an answer')
            if msg[0] == 'done':
                last = msg; break
        _, cautious, witnesses, exhausted = last
        if cautious is None:  # no model at all
            result = dict(label='UNKNOWN', reason='identity_inconsistent', certificate=True, mappings=[]) \
                if exhausted else dict(label='UNKNOWN', reason='budget', certificate=False, mappings=[])
        elif not exhausted:
            result = dict(label='UNKNOWN', reason='budget', certificate=False, mappings=witnesses)
        elif cautious == [0]:
            result = dict(label='SATISFIES', reason='cautious_consequence', certificate=True, mappings=witnesses[-1:])
        elif cautious == [2]:
            result = dict(label='VIOLATES', reason='cautious_consequence', certificate=True, mappings=witnesses[-1:])
        else:  # t(1) cautious, or empty cautious set: states disagree or evidence missing
            result = dict(label='UNKNOWN', reason='cautious_consequence', certificate=True, mappings=witnesses)
    except Deadline:
        result = dict(label='UNKNOWN', reason='budget', certificate=False, mappings=[])
    except RuntimeError as exc:
        result = dict(label='UNKNOWN', reason='runtime_error', certificate=False, mappings=[], detail=str(exc)[:300])
    finally:
        if proc.is_alive():
            proc.kill()
        proc.join()
        parent.close()
    return _finish(result, start, budget, 'asp_cautious')


METHODS = {'enum_glasgow': enum_glasgow, 'enum_nx': enum_nx, 'asp_cautious': asp_cautious}
