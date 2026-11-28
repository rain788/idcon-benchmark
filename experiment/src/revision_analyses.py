"""Revision R1 analyses that need task inputs (registered as A4, A5, A6 and the
structure table). Writes results/revision_r1/analyses.json, which
analysis_tables.py turns into paper tables and macros.

A4 learned no-search prior: HistGradientBoostingClassifier (scikit-learn
   defaults, random_state=0), leave-one-ancestor-out, on features that need no
   search (metadata, ancestor statistics, observation-table statistics).
A5 symmetry: lower bound on UNKNOWN references explained by pattern
   automorphisms alone (pynauty generators of Aut(Q) that preserve anchors,
   metric-edge lengths and unary domains, plus 64 random products), applied to
   an admissible identity (Hard: the construction map; HPRD suites: a replayed
   method witness).
A6 summary of results/revision_r1/hprd_embedding_counts.jsonl.
Structure statistics per suite (Table 2).
"""
import collections, json, random, statistics, sys
from pathlib import Path
import numpy as np
import networkx as nx
sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_idcon as sc
from coordination_confirmation_data import legal
from projection_engine import graph_data
from full_benchmark_methods import rank_of

ROOT = sc.ROOT
OUT = ROOT / 'results/revision_r1/analyses.json'
SUITES = ['idcon_hard', 'idcon_hprd', 'idcon_hprd_x']


def load_suite(study):
    data = ROOT / 'data/processed' / study
    manifest = {}
    for p in sorted(data.glob('manifest*.json')):
        manifest.update({r['task_id']: r for r in json.loads(p.read_text())})
    ancestors = {a['group_id']: a for a in json.loads((data / 'ancestors.json').read_text())}
    _, refs, _ = sc.score(study)
    return manifest, ancestors, refs


def read(p):
    return json.loads(Path(p).read_text())


# ------------------------------------------------------------------ A4 learned prior
def features(rec, anc, identity, observed):
    g, q, anchors = graph_data(identity)
    deg = np.array([g.degree[u] for u in range(len(g))])
    tables = {int(r): np.array(v) for r, v in observed['role_states'].items()}
    f = dict(entities=rec['entities'], roles=rec['roles'], host_edges=g.number_of_edges(),
             query_edges=q.number_of_edges(), anchors=len(anchors),
             metric_edges=sum(l is not None for _, _, l, _ in identity['role_edges']),
             query_components=nx.number_connected_components(q), checked=len(tables),
             global_state=observed['global_state'])
    for k, v in (rec.get('params') or {}).items():
        if isinstance(v, (int, float)):
            f['param_' + k] = v
        elif isinstance(v, list):
            f['param_n_' + k] = len(v)
    stats = []
    for r, t in tables.items():
        feas = deg >= q.degree[r]
        dom = identity.get('role_domains', {}).get(str(r))
        if dom is not None:
            mask = np.zeros(len(deg), bool); mask[dom] = True; feas &= mask
        row = []
        for x in (0, 1, 2):
            row += [float(np.mean(t == x)), float(np.mean(t[feas] == x)) if feas.any() else 0.0]
        stats.append(row)
    stats = np.array(stats)
    for j, name in enumerate(['S_all', 'S_feas', 'U_all', 'U_feas', 'V_all', 'V_feas']):
        f[f'min_{name}'] = float(stats[:, j].min()); f[f'mean_{name}'] = float(stats[:, j].mean())
        f[f'max_{name}'] = float(stats[:, j].max())
    f['roles_without_S'] = int(sum(1 for r, t in tables.items() if not np.any(t == 0)))
    f['roles_without_nonS'] = int(sum(1 for r, t in tables.items() if not np.any(t > 0)))
    return f


def learned_prior(study, manifest, ancestors, refs):
    from sklearn.ensemble import HistGradientBoostingClassifier
    tasks = sorted(t for t, r in refs.items() if r['complete'])
    X, y, groups, cats = [], [], [], {}
    keys = None
    for t in tasks:
        rec = manifest[t]
        identity = read(ROOT / rec['identity_file']); observed = read(ROOT / rec['tables_file'])
        f = features(rec, ancestors[rec['group_id']], identity, observed)
        for c in ('family', 'construction', 'variant', 'scenario', 'query_set'):
            if rec.get(c) is not None:
                f['cat_' + c] = cats.setdefault(c, {}).setdefault(rec[c], len(cats.get(c, {})))
        X.append(f); y.append(refs[t]['label']); groups.append(rec['group_id'])
    keys = sorted({k for f in X for k in f})
    A = np.array([[f.get(k, np.nan) for k in keys] for f in X], float)
    catmask = np.array([k.startswith('cat_') for k in keys])
    yv = np.array(y); gv = np.array(groups)
    pred = np.empty(len(y), object)
    for gid in sorted(set(groups)):
        test = gv == gid; train = ~test
        labels = sorted(set(yv[train]))
        if len(labels) == 1:
            pred[test] = labels[0]; continue
        model = HistGradientBoostingClassifier(random_state=0, categorical_features=catmask)
        model.fit(A[train], yv[train])
        pred[test] = model.predict(A[test])
    correct = int(sum(p == t for p, t in zip(pred, yv)))
    by = collections.Counter((t, p == t) for p, t in zip(pred, yv))
    return dict(correct=correct, tasks=len(y), features=len(keys),
                by_label={lb: [by[(lb, True)], by[(lb, True)] + by[(lb, False)]] for lb in sorted(set(yv))},
                predictions={t: p for t, p in zip(tasks, pred)})


# ------------------------------------------------------------------ A5 symmetry
def aut_generators(identity, q, anchors, classes):
    import pynauty
    k = q.number_of_nodes()
    adj = collections.defaultdict(set); extra = []
    lengths = {}
    for r, s, l, _ in identity['role_edges']:
        if l is None:
            adj[r].add(s); adj[s].add(r)
        else:
            lengths.setdefault(round(l, 6), []).append((r, s))
    nxt = k
    colors = collections.defaultdict(set)
    for r in range(k):
        colors[('role',) + classes(r)].add(r)
    for i, (l, es) in enumerate(sorted(lengths.items())):
        for r, s in es:
            v = nxt; nxt += 1
            adj[v].update((r, s)); adj[r].add(v); adj[s].add(v)
            colors[('metric', i)].add(v)
    g = pynauty.Graph(nxt, adjacency_dict={u: sorted(v) for u, v in adj.items()},
                      vertex_coloring=[colors[c] for c in sorted(colors, key=str)])
    gens = pynauty.autgrp(g)[0]
    return [tuple(p[:k]) for p in gens]


def symmetry(study, manifest, refs):
    maps = read(ROOT / 'data/protected' / study / 'construction_maps.json')
    witnesses = {}
    if not maps:  # HPRD suites: use a replayed witness from any certified method
        rows = sc.load_jsonl(ROOT / 'results' / study / 'predictions*.jsonl')
        for p in rows:
            if p.get('certificate') and p.get('mappings') and p['task_id'] not in witnesses:
                witnesses[p['task_id']] = p['mappings'][0]
    rng = random.Random(20261127)
    out = collections.Counter(); examples = []
    for t, r in sorted(refs.items()):
        if not r['complete'] or r['label'] != 'UNKNOWN':
            continue
        rec = manifest[t]
        identity = read(ROOT / rec['identity_file']); observed = read(ROOT / rec['tables_file'])
        tables = {int(x): v for x, v in observed['role_states'].items()}
        g, q, anchors = graph_data(identity)
        y = maps.get(rec['group_id']) or witnesses.get(t)
        if y is None or not legal(identity, y):
            out['no_admissible_identity'] += 1; continue
        doms = {int(x): frozenset(v) for x, v in identity.get('role_domains', {}).items()}
        classes = lambda role: (('anchor', role) if role in anchors else ('free',)) + ((hash(doms[role]),) if role in doms else ())
        gens = aut_generators(identity, q, anchors, classes)
        base = rank_of(y, tables, observed['global_state'])
        if base == 1:
            out['state_U_identity'] += 1; continue
        elems = list(gens)
        for _ in range(64):
            if not gens:
                break
            perm = list(range(len(y)))
            for _ in range(rng.randint(2, 6)):
                gnr = rng.choice(gens); perm = [gnr[i] for i in perm]
            elems.append(tuple(perm))
        found = False
        for s in elems:
            y2 = [y[s[i]] for i in range(len(y))]
            assert legal(identity, y2)
            if rank_of(y2, tables, observed['global_state']) != base:
                found = True; break
        out['symmetry_explained' if found else 'not_explained_by_sampled_symmetry'] += 1
        if gens:
            out['has_nontrivial_automorphism'] += 1
    out['unknown_references'] = sum(1 for r in refs.values() if r['complete'] and r['label'] == 'UNKNOWN')
    return dict(out)


# ------------------------------------------------------------------ structure stats
def structure(study, manifest, ancestors):
    rows = collections.defaultdict(list)
    seen = set()
    for t, rec in manifest.items():
        if rec['group_id'] in seen:
            continue
        seen.add(rec['group_id'])
        identity = read(ROOT / rec['identity_file'])
        g, q, anchors = graph_data(identity)
        deg = np.array([d for _, d in g.degree()])
        key = rec['variant'] if study == 'idcon_hard' else study
        cand = []
        for r in q:
            ok = deg >= q.degree[r]
            dom = identity.get('role_domains', {}).get(str(r))
            if dom is not None:
                m = np.zeros(len(deg), bool); m[dom] = True; ok &= m
            if r in anchors:
                continue
            cand.append(float(ok.mean()))
        cl = rows.setdefault(('clust', study), {})
        if study == 'idcon_hard' or not cl:
            cl[rec['group_id']] = nx.average_clustering(g)
        rows[key].append(dict(family=rec['family'], n=len(g), mean_degree=2 * g.number_of_edges() / len(g),
                              cv=float(deg.std() / deg.mean()), clustering=list(cl.values())[-1],
                              edges_per_role=q.number_of_edges() / q.number_of_nodes(),
                              candidate=statistics.mean(cand) if cand else None))
    res = {}
    for key, vals in rows.items():
        if isinstance(key, tuple):
            continue
        med = lambda f: statistics.median(v[f] for v in vals)
        fam = collections.defaultdict(list)
        for v in vals:
            fam[v['family']].append(v['cv'])
        res[key] = dict(ancestors=len(vals), n=med('n'), mean_degree=med('mean_degree'), cv=med('cv'),
                        cv_family_range=[min(statistics.median(x) for x in fam.values()),
                                         max(statistics.median(x) for x in fam.values())],
                        clustering=med('clustering'), edges_per_role=med('edges_per_role'),
                        candidate=med('candidate'))
    return res


def counts_summary():
    p = ROOT / 'results/revision_r1/hprd_embedding_counts.jsonl'
    if not p.exists():
        return None
    rows = [json.loads(l) for l in p.read_text().splitlines()]
    out = {}
    for suite in ('idcon_hprd', 'idcon_hprd_x'):
        sub = [r for r in rows if r['suite'] == suite]
        for kind in ('full_labels', 'idcon_space'):
            c = [r[kind] for r in sub]
            out[f'{suite}|{kind}'] = dict(
                queries=len(c), complete=sum(x['complete'] for x in c),
                zero=sum(x['complete'] and x['count'] == 0 for x in c),
                unique=sum(x['complete'] and x['count'] == 1 for x in c),
                more_than_one=sum((x['count'] or 0) > 1 for x in c),
                at_least_1000=sum((x['count'] or 0) >= 1000 for x in c),
                median_count=statistics.median(x['count'] or 0 for x in c),
                timeouts=sum(not x['complete'] for x in c))
    return out


def main():
    res = dict(learned_prior={}, symmetry={}, structure={})
    for study in SUITES:
        manifest, ancestors, refs = load_suite(study)
        lp = learned_prior(study, manifest, ancestors, refs)
        res['learned_prior'][study] = {k: v for k, v in lp.items() if k != 'predictions'}
        res.setdefault('learned_predictions', {})[study] = lp['predictions']
        res['symmetry'][study] = symmetry(study, manifest, refs)
        res['structure'].update({f'{study}|{k}': v for k, v in structure(study, manifest, ancestors).items()})
        print(study, res['learned_prior'][study], res['symmetry'][study], flush=True)
    res['counts'] = counts_summary()
    ov = ROOT / 'results/revision_r1/overhead.json'
    res['overhead'] = json.loads(ov.read_text()) if ov.exists() else None
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print('WROTE', OUT)


if __name__ == '__main__':
    main()
