"""Revision R1: how common are non-unique embeddings in the third-party workload?

For every query of IdCon-HPRD (Sun & Luo dense-16, queries 1-100) and of
IdCon-HPRD-X, count admissible embeddings with the Glasgow Subgraph Solver
(--count-solutions, 30 s per count), twice:
  full_labels   the third-party semantics: every query vertex must match its
                own label (Glasgow's native vertex labels; no IdCon choice);
  idcon_space   the IdCon identity space: checked roles free, the other roles
                restricted to their label (labelled-gadget encoding).
A count that hits the time limit is reported as a lower bound.
Output: results/revision_r1/hprd_embedding_counts.jsonl
"""
import json, os, re, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from external_hprd import parse
from projection_engine import graph_data
from revision_baselines import domains_of, GLASGOW

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/revision_r1/hprd_embedding_counts.jsonl'
LIMIT = 30


def run_count(pattern_lines, target_text):
    with tempfile.TemporaryDirectory(prefix='idcon_count_', dir='/dev/shm') as tmp:
        p = Path(tmp) / 'p.csv'; t = Path(tmp) / 't.csv'
        p.write_text('\n'.join(pattern_lines) + '\n'); t.write_text(target_text)
        t0 = time.perf_counter()
        out = subprocess.run([str(GLASGOW), '--count-solutions', '--format', 'csv', '--timeout', str(LIMIT),
                              str(p), str(t)], capture_output=True, text=True)
        sec = time.perf_counter() - t0
    status = re.search(r'^status = (\w+)', out.stdout, re.M)
    count = re.search(r'^solution_count = (\d+)', out.stdout, re.M)
    return dict(status=status.group(1) if status else 'error', count=int(count.group(1)) if count else None,
                seconds=round(sec, 3), complete=bool(status) and status.group(1) in ('true', 'false'))


def main():
    labels, edges = parse(ROOT / 'data/raw/hprd_sun_luo/HPRD.graph')
    target_full = '\n'.join([f't{u},,L{l}' for u, l in sorted(labels.items())] +
                            [f't{u},t{v}' for u, v in sorted(set(tuple(sorted(e)) for e in edges))]) + '\n'
    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if OUT.exists():
        done = {json.loads(l)['group_id'] for l in OUT.read_text().splitlines()}
    with OUT.open('a') as stream:
        for suite in ('idcon_hprd', 'idcon_hprd_x'):
            data = ROOT / 'data/processed' / suite
            for anc in json.loads((data / 'ancestors.json').read_text()):
                if anc['group_id'] in done:
                    continue
                qlab = anc['query_labels']
                ident = json.loads((data / 'identities' / f"{anc['group_id']}.json").read_text())
                pnodes = [f'p{r},,L{l}' for r, l in enumerate(qlab)]
                pedges = [f'p{r},p{s}' for r, s, _, _ in ident['role_edges']]
                full = run_count(pnodes + pedges, target_full)
                # IdCon identity space via the labelled-gadget encoding
                g, q, anchors = graph_data(ident); dom = domains_of(ident, g, q, anchors)
                n = len(g)
                pn = [f'p{r},,B' for r in q]; pe = [f'p{r},p{s}' for r, s in q.edges]
                tn = [f't{u},,B' for u in g]; te = [f't{u},t{v}' for u, v in g.edges]
                for r, d in dom.items():
                    if len(d) == n:
                        continue
                    pn.append(f'pr{r},,R{r}'); pe.append(f'p{r},pr{r}')
                    for u in sorted(d):
                        tn.append(f'tr{r}_{u},,R{r}'); te.append(f't{u},tr{r}_{u}')
                space = run_count(pn + pe, '\n'.join(tn + te) + '\n')
                row = dict(suite=suite, group_id=anc['group_id'], query=anc['query'], roles=anc['roles'],
                           query_edges=anc['query_edges'], query_set=anc.get('query_set', 'dense_16'),
                           checked=len(anc['checked_roles']), full_labels=full, idcon_space=space)
                stream.write(json.dumps(row) + '\n'); stream.flush()
                print('COUNT', anc['group_id'], full['count'], full['status'], space['count'], space['status'], flush=True)


if __name__ == '__main__':
    main()
