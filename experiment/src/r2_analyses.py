"""Revision R2 analyses (design: results/revision_r2/design.json).

python r2_analyses.py compute      -> results/revision_r2/analyses_r2.json (slow parts:
                                      learned priors and structure of the new suites,
                                      automorphism-corrected embedding counts)
Called from analysis_tables.py, which turns analyses_r2.json plus the frozen
records into the paper's R2 tables and macros (tables/r2_*.tex, results_macros_r2.tex).
Registered R2 analyses and Amendment 5 post hoc analyses are labelled as such.
"""
import collections
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_idcon as sc  # noqa: E402

ROOT = sc.ROOT
R2 = ROOT / 'results/revision_r2'
OUT = R2 / 'analyses_r2.json'
LABELS = ['SATISFIES', 'VIOLATES', 'UNKNOWN', 'EMPTY']
LEGACY = ['eg_icaf', 'lad_sv_early']
SOUND_R1 = ['lad_state', 'glasgow', 'whole_cp', 'traditional_cp', 'enum_glasgow', 'enum_nx', 'asp_cautious']


def jl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def anc_par(rows, m, sel=None, field='par2_ms'):
    g = collections.defaultdict(list)
    for r in rows:
        if r['method'] == m and r['assessed'] and (sel is None or sel(r)):
            g[r['group_id']].append(r[field])
    return statistics.mean(statistics.mean(v) for v in g.values()) if g else None


def summ(rows, methods, sel=None):
    out = {}
    for m in methods:
        sub = [r for r in rows if r['method'] == m and r['assessed'] and (sel is None or sel(r))]
        if not sub:
            continue
        out[m] = dict(assessed=len(sub), correct=sum(r['correct'] for r in sub),
                      wrong=sum(r['answered'] and not r['correct'] for r in sub),
                      certified_wrong=sum(r['certified_wrong'] for r in sub),
                      unanswered=sum(not r['answered'] for r in sub), par2_ms=anc_par(rows, m, sel),
                      by_label={lb: [sum(r['correct'] for r in sub if r['reference'] == lb),
                                     sum(1 for r in sub if r['reference'] == lb)] for lb in LABELS})
    return out


def vbs(rows, methods, sel=None, repeat=None):
    per = collections.defaultdict(bool)
    ref = {}
    for r in rows:
        if not r['assessed'] or (sel and not sel(r)) or (repeat is not None and r['repeat'] != repeat):
            continue
        k = (r['task_id'], r['repeat'])
        ref[k] = r['reference']
        if r['method'] in methods and r['correct']:
            per[k] = True
    uns = [k for k in ref if not per[k]]
    return dict(runs=len(ref), unsolved=len(uns), by_label=dict(collections.Counter(ref[k] for k in uns)))


# ------------------------------------------------------------------ predicates
def table_decided(ref_row, scenario):
    """Two of three states excluded by the observation tables in a scenario whose
    construction embedding is admissible by design (all but 'perturbed')."""
    pr = sum(1 for s in ref_row['states'].values() if s.get('engine') == 'predicate_range')
    return scenario != 'perturbed' and pr == 2


# ------------------------------------------------------------------ compute (slow)
def compute():
    import revision_analyses as ra
    res = dict(learned_prior={}, learned_predictions={}, structure={})
    for study in ('idcon_hard_x', 'idcon_cite'):
        manifest, ancestors, refs = ra.load_suite(study)
        if not any(r['complete'] for r in refs.values()):
            continue
        lp = ra.learned_prior(study, manifest, ancestors, refs)
        res['learned_prior'][study] = {k: v for k, v in lp.items() if k != 'predictions'}
        res['learned_predictions'][study] = lp['predictions']
        res['structure'].update({f'{study}|{k}': v for k, v in ra.structure(study, manifest, ancestors).items()})
    res['automorphism'] = automorphism_counts()
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print('WROTE', OUT)


def automorphism_counts():
    """Amendment 5: embeddings per query divided by |Aut(Q)| (label-preserving),
    i.e. the number of embedding orbits; > 1 means genuinely different placements."""
    import networkx as nx
    from networkx.algorithms.isomorphism import GraphMatcher, categorical_node_match
    from external_hprd import parse
    counts = jl(ROOT / 'results/revision_r1/hprd_embedding_counts.jsonl')
    out = {}
    for suite, qdir in (('idcon_hprd', ROOT / 'data/raw/hprd_sun_luo/query_graph'),
                        ('idcon_hprd_x', ROOT / 'data/raw/cemr_hprd/query_graph')):
        rows = [r for r in counts if r['suite'] == suite]
        multi = multi_orbit = 0
        for r in rows:
            lab, edges = parse(qdir / r['query'])
            g = nx.Graph()
            for u, l in lab.items():
                g.add_node(u, l=l)
            g.add_edges_from(edges)
            aut = sum(1 for _ in GraphMatcher(g, g, node_match=categorical_node_match('l', None)).isomorphisms_iter())
            c = r['full_labels']['count']
            multi += c > 1
            multi_orbit += c / aut > 1
        out[suite] = dict(queries=len(rows), more_than_one=multi, more_than_one_orbit=multi_orbit)
    return out


# ------------------------------------------------------------------ tables (fast)
def gather():
    """Everything the paper needs from R2, computed from records (fast)."""
    an = json.loads(OUT.read_text()) if OUT.exists() else {}
    an1 = json.loads((ROOT / 'results/revision_r1/analyses.json').read_text())
    res = {}
    # --- legacy disclosure (Amendment 5)
    leg = {}
    for study in ('idcon_hard', 'idcon_hprd'):
        rows, refs, man = sc.score(study, preds='r1')
        s = summ(rows, LEGACY)
        exact = [m for m in SOUND_R1 if any(r['method'] == m for r in rows)]
        leg[study] = dict(methods=s, vbs_r1=vbs(rows, exact), vbs_with_eg=vbs(rows, exact + ['eg_icaf']),
                          vbs_with_both=vbs(rows, exact + LEGACY), lad=summ(rows, ['lad_state']).get('lad_state'))
    res['legacy'] = leg
    # --- IdCon-Hard sensitivity and budgets
    rows, refs, man = sc.score('idcon_hard')
    rows = [r for r in rows if r['method'] not in LEGACY]
    methods = sorted({r['method'] for r in rows})
    decided = {t for t, r in refs.items() if table_decided(r, man[t]['scenario'])}
    res['sensitivity'] = dict(
        table_decided_tasks=len(decided),
        decoy_s_tasks=sum(1 for t in man if man[t]['scenario'] == 'decoy_s'),
        decided_by_scenario=dict(collections.Counter(man[t]['scenario'] for t in decided)),
        all=summ(rows, methods),
        no_decoy_s=summ(rows, methods, lambda r: r['scenario'] != 'decoy_s'),
        nontrivial=summ(rows, methods, lambda r: r['task_id'] not in decided))
    # budgets, repeat 0: 2 s records, 10 s (R1) and 60 s (R2) reruns
    b10, _, _ = sc.score('idcon_hard', preds='b10')
    b60, _, _ = sc.score('idcon_hard', preds='b60')
    ok = collections.defaultdict(lambda: {2: False, 10: False, 60: False})
    tasks = sorted(t for t, r in refs.items() if r['complete'])
    for r in rows:
        if r['repeat'] == 0 and r['correct']:
            for b in (2, 10, 60):
                ok[(r['task_id'], r['method'])][b] = True
    for r in b10:
        if r['correct']:
            ok[(r['task_id'], r['method'])][10] = ok[(r['task_id'], r['method'])][60] = True
    for r in b60:
        if r['correct']:
            ok[(r['task_id'], r['method'])][60] = True
    sound = [m for m in methods if m != 'first_match']
    def vb(ms, b):
        return sum(1 for t in tasks if not any(ok[(t, m)][b] for m in ms))
    res['budget_hard'] = dict(
        tasks=len(tasks),
        lad={b: sum(ok[(t, 'lad_state')][b] for t in tasks) for b in (2, 10, 60)},
        glasgow_staged={b: sum(ok[(t, 'glasgow_staged')][b] for t in tasks) for b in (2, 10, 60)},
        vbs_r1_unsolved={b: vb([m for m in sound if m in SOUND_R1], b) for b in (2, 10, 60)},
        vbs_all_unsolved={b: vb(sound, b) for b in (2, 10, 60)},
        vbs_all_unsolved_60_by_label=dict(collections.Counter(
            refs[t]['label'] for t in tasks if not any(ok[(t, m)][60] for m in sound))),
        b60_runs=len(b60), b60_by_method=dict(collections.Counter(r['method'] for r in b60)))
    # --- runtime errors (Amendment 5)
    err = {}
    for study in ('idcon_hard', 'idcon_hprd', 'idcon_hprd_x', 'idcon_hard_x', 'idcon_cite'):
        if not (ROOT / 'results' / study).exists():
            continue
        c = collections.Counter()
        n = collections.Counter()
        for p in sorted((ROOT / 'results' / study).glob('predictions*.jsonl')):
            for r in jl(p):
                if r['method'] in LEGACY:
                    continue
                n[r['method']] += 1
                if r.get('reason') == 'runtime_error':
                    c[r['method']] += 1
        err[study] = dict(errors=dict(c), runs=dict(n))
    res['runtime_errors'] = err
    # --- prior overlap on IdCon-Hard (Amendment 5)
    lp = an1['learned_predictions']['idcon_hard']
    comp = {t: r for t, r in refs.items() if r['complete']}
    def loo(keys):
        pred = {}
        for t in comp:
            rec = man[t]
            pool = collections.Counter(comp[u]['label'] for u in comp if man[u]['group_id'] != rec['group_id']
                                       and all(man[u][k] == rec[k] for k in keys))
            pred[t] = pool.most_common(1)[0][0] if pool else None
        return pred
    ps = loo(['scenario'])
    pm = loo(['scenario', 'entities', 'construction', 'variant'])
    wrong_all = [t for t in comp if ps[t] != comp[t]['label'] and pm[t] != comp[t]['label'] and lp.get(t) != comp[t]['label']]
    wrong_learned = [t for t in comp if lp.get(t) != comp[t]['label']]
    res['prior_overlap_hard'] = dict(tasks=len(comp), wrong_learned=len(wrong_learned), wrong_all_three=len(wrong_all))
    # --- calibration of the R2 machine
    cal, _, _ = sc.score('idcon_hard', preds='r2calib')
    old = {(r['task_id'], r['method']): r for r in rows if r['repeat'] == 0}
    pairs = [(c, old[(c['task_id'], c['method'])]) for c in cal if (c['task_id'], c['method']) in old]
    both = [(c['seconds'], o['seconds']) for c, o in pairs if c['correct'] and o['correct']]
    res['calibration'] = dict(runs=len(pairs), outcome_agree=sum(c['outcome'] == o['outcome'] for c, o in pairs),
                              both_correct=len(both),
                              median_ratio=statistics.median(a / b for a, b in both) if both else None,
                              wrong=sum(c['certified_wrong'] for c, _ in pairs))
    # --- new suites
    res['new'] = {}
    for study, budgets in (('idcon_hard_x', ('main', 'b10', 'b60')), ('idcon_cite', ('main', 'b10'))):
        if not (ROOT / 'results' / study).exists():
            continue
        entry = {}
        refs_n = None
        for b in budgets:
            rws, refs_n, man_n = sc.score(study, preds=b)
            ms = sorted({r['method'] for r in rws})
            entry[b] = dict(summary=summ(rws, ms), runs=len(rws))
            snd = [m for m in ms if m != 'first_match']
            entry[b]['vbs'] = vbs(rws, snd)
            entry[b]['vbs_rep0'] = vbs(rws, snd, repeat=0)
        complete = [r for r in refs_n.values() if r['complete']]
        entry['tasks'] = len(man_n)
        entry['ancestors'] = len({m['group_id'] for m in man_n.values()})
        entry['complete'] = len(complete)
        entry['labels'] = dict(collections.Counter(r['label'] for r in complete))
        mkeys = {'idcon_hard_x': ['scenario', 'construction', 'variant'], 'idcon_cite': ['scenario', 'family', 'query_set']}[study]
        comp_n = {t: r for t, r in refs_n.items() if r['complete']}
        entry['prior_scenario'] = sc.prior_accuracy(comp_n, man_n, ['scenario']) if comp_n else (0, 0)
        entry['prior_meta'] = sc.prior_accuracy(comp_n, man_n, mkeys) if comp_n else (0, 0)
        lpn = an.get('learned_prior', {}).get(study)
        entry['prior_learned'] = (lpn['correct'], lpn['tasks']) if lpn else None
        # budget ladder on repeat 0 (Hard-X: 2 s, 10 s, 60 s; Cite: 2 s, 10 s)
        okn = collections.defaultdict(dict)
        for b, secs in (('main', 2), ('b10', 10), ('b60', 60)):
            if b not in budgets:
                continue
            rws, _, _ = sc.score(study, preds=b)
            for r in rws:
                if r['repeat'] == 0 and r['correct']:
                    okn[(r['task_id'], r['method'])][secs] = True
        tasks_n = sorted(comp_n)
        ladder = {}
        for m in sorted({k[1] for k in okn} | set(entry['main']['summary'])):
            ladder[m] = {}
            for secs in (2, 10, 60):
                ladder[m][secs] = sum(1 for t in tasks_n if any(okn[(t, m)].get(s) for s in (2, 10, 60) if s <= secs))
        snd = [m for m in ladder if m != 'first_match']
        entry['ladder'] = ladder
        entry['ladder_vbs_unsolved'] = {secs: sum(1 for t in tasks_n if not any(
            okn[(t, m)].get(s) for m in snd for s in (2, 10, 60) if s <= secs)) for secs in (2, 10, 60)}
        entry['first_match_wrong_on_unknown'] = None
        res['new'][study] = entry
    # --- independent check
    idc = []
    for p in sorted(R2.glob('idcheck.w*.jsonl')):
        idc += jl(p)
    if idc:
        sample = {}
        for p in sorted(R2.glob('idcheck_part*.json')):
            for it in json.loads(p.read_text()):
                sample[it['task_id']] = it
        refs_all = {}
        for study in ('idcon_hard', 'idcon_hprd_x', 'idcon_hard_x', 'idcon_cite'):
            _, rr, _ = sc.score(study)
            refs_all.update(rr)
        tab = collections.defaultdict(lambda: collections.Counter())
        disagree = []
        neg_stats = collections.Counter()
        for row in idc:
            it = sample[row['task_id']]
            key = (it['suite'], it['why'])
            ref = refs_all.get(row['task_id'])
            reflab = ref['label'] if ref and ref['complete'] else 'UNASSESSED'
            tab[key]['tasks'] += 1
            if row['label'] == 'UNRESOLVED':
                tab[key]['unresolved'] += 1
            elif reflab == 'UNASSESSED':
                tab[key]['settles_unassessed'] += 1
            elif row['label'] == reflab:
                tab[key]['agree'] += 1
            else:
                tab[key]['disagree'] += 1
                disagree.append((row['task_id'], row['label'], reflab))
            for s in row['states'].values():
                neg_stats[s['how']] += 1
        res['idcheck'] = dict(table={f'{a}|{b}': dict(v) for (a, b), v in tab.items()}, disagree=disagree,
                              how=dict(neg_stats))
    # --- overhead on IdCon-Hard
    oh = R2 / 'overhead_hard.json'
    res['overhead_hard'] = json.loads(oh.read_text()) if oh.exists() else None
    res['automorphism'] = an.get('automorphism')
    res['structure'] = an.get('structure')
    return res


if __name__ == '__main__':
    if sys.argv[1] == 'compute':
        compute()
    elif sys.argv[1] == 'gather':
        print(json.dumps(gather(), indent=1, default=str)[:20000])
