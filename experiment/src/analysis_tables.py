"""Build the paper's tables, LaTeX macros and a JSON summary (revision R1).

python analysis_tables.py <paper_dir>

Inputs: frozen v1 records (IdCon-Hard, IdCon-HPRD), R1 records (new baselines,
IdCon-HPRD-X, 10 s runs), R1 references (data/protected/*/references_r1*.jsonl
override v1 references where present) and results/revision_r1/analyses.json
(revision_analyses.py). The legacy methods LAD-SV and EG-ICAF and the legacy
IdCon-Core suite are not analysed (Amendment 4).
"""
import collections
import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_idcon as sc

ROOT = sc.ROOT
SUITES = [('hard', 'idcon_hard', 'IdCon-Hard'), ('hprd', 'idcon_hprd', 'IdCon-HPRD'),
          ('hprdx', 'idcon_hprd_x', 'IdCon-HPRD-X')]
NAMES = {'lad_state': 'LAD', 'glasgow': 'Glasgow', 'glasgow_staged': 'Glasgow-staged',
         'whole_cp': 'CP-SAT', 'traditional_cp': 'Trad-CP', 'enum_glasgow': 'Enum-Glasgow',
         'enum_nx': 'Enum-VF2', 'asp_cautious': 'ASP-cautious', 'sat_cadical': 'SAT',
         'first_match': 'First-match'}
ORDER = ['lad_state', 'glasgow', 'glasgow_staged', 'whole_cp', 'traditional_cp',
         'enum_glasgow', 'enum_nx', 'asp_cautious', 'sat_cadical', 'first_match']
LEGACY = {'lad_sv_early', 'eg_icaf'}
NEW = {'enum_glasgow', 'enum_nx', 'asp_cautious'}
NEW2 = {'sat_cadical'}  # revision R2
LABELS = ['SATISFIES', 'VIOLATES', 'UNKNOWN', 'EMPTY']
B10_METHODS = ['lad_state', 'glasgow', 'glasgow_staged', 'whole_cp', 'enum_glasgow']


def posthoc(m, tag):
    """Glasgow-staged was added after scoring on the v1 suites (v1 Amendment 3)."""
    return m == 'glasgow_staged' and tag in ('hard', 'hprd')


def show(m, tag=None):
    return (NAMES[m] + (r'$^\dagger$' if tag and posthoc(m, tag) else '') + (r'$^\ast$' if m in NEW else '')
            + (r'$^\ddagger$' if m in NEW2 else ''))


def exact(tag):
    return [m for m in ORDER if m != 'first_match' and not posthoc(m, tag)]


def fmt(x, d=1):
    return '--' if x is None else f'{x:,.{d}f}'


def macro(name, value):
    return f'\\newcommand{{\\{name}}}{{{value}}}\n'


def key(m):
    k = NAMES[m].replace('-', '').replace(' ', '')
    for d, w in (('2', 'Two'), ('1', 'One'), ('0', 'Zero')):
        k = k.replace(d, w)
    return k


LABEL_TEX = {'SATISFIES': r'\Sat{}', 'VIOLATES': r'\Vio{}', 'UNKNOWN': r'\Unk{}', 'EMPTY': r'\Emp{}'}


def join_words(items):
    items = list(items)
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]


def extra_macros(out, data):
    m = ''
    tot_t = sum(out[t]['tasks'] for t, _, _ in SUITES)
    tot_a = sum(out[t]['ancestors'] for t, _, _ in SUITES)
    m += macro('totalTasks', f'{tot_t:,}') + macro('totalAncestors', tot_a)
    # first-match breakdown on IdCon-HPRD
    rows = data['hprd'][0]
    w = [r for r in rows if r['method'] == 'first_match' and r['assessed'] and r['answered'] and not r['correct']]
    m += macro('hprdFirstWrongSpecTrue', sum(r['scenario'] == 'spec_true' for r in w))
    m += macro('hprdFirstWrongSpecTrueVio', sum(r['scenario'] == 'spec_true' and r['outcome'] == 'VIOLATES' for r in w))
    m += macro('hprdFirstWrongSpecTrueSat', sum(r['scenario'] == 'spec_true' and r['outcome'] == 'SATISFIES' for r in w))
    m += macro('hprdFirstWrongSpecWrong', sum(r['scenario'] == 'spec_wrong' for r in w))
    # repeat agreement (all non-legacy methods with two repeats)
    for t in ('hard', 'hprd', 'hprdx'):
        by = collections.defaultdict(dict)
        for r in data[t][0]:
            by[(r['task_id'], r['method'])][r['repeat']] = r['outcome']
        pairs = [v for v in by.values() if len(v) == 2]
        out[t]['repeat_agree'] = (sum(v[0] == v[1] for v in pairs), len(pairs))
        m += macro(f'{t}RepeatAgreePct', fmt(100 * out[t]['repeat_agree'][0] / len(pairs)))
    # witnesses
    wr = json.loads((ROOT / 'results/witness_replay.json').read_text())
    tot = sum(c for st in wr.values() for k, c in st['by_method'].items()
              if k.split('|')[0] not in LEGACY and k.endswith('|True'))
    bad = sum(c for st in wr.values() for k, c in st['by_method'].items()
              if k.split('|')[0] not in LEGACY and k.endswith('|False'))
    assert bad == 0, 'witness replay failures'
    m += macro('witnessTotal', f'{tot:,}')
    out['witnesses'] = dict(total=tot, failures=bad)
    # strata sentence
    parts = []
    for t, label in (('hard', 'IdCon-Hard'), ('hprdx', 'IdCon-HPRD-X')):
        best = collections.defaultdict(list)
        for st, v in out[t]['strata'].items():
            rk = v['rank']
            ns = rk['ci95'][0] <= 0 <= rk['ci95'][1]  # interval of the difference to the runner-up includes 0
            best[rk['best']].append(f"{st} ({rk['prob'][rk['best']]:.2f}" + (', n.s.' if ns else '') + ')')
        items = [f'{show(b, t)} in {join_words(v)}' for b, v in best.items()]
        parts.append(f'on {label} the best method is ' + '; '.join(items))
    m += macro('strataSentence', ', and '.join(parts))
    v = out['hard']['vbs_unsolved_by_label']
    m += macro('vbsUnsolvedSentence', join_words(f'{v[k]} are {LABEL_TEX[k]}' for k in LABELS if v.get(k)))
    for lb, short in (('SATISFIES', 'Sat'), ('UNKNOWN', 'Unk'), ('VIOLATES', 'Vio'), ('EMPTY', 'Emp')):
        for meth in ORDER:
            s_ = out['hard']['methods'].get(meth)
            if s_:
                m += macro(f'hard{key(meth)}{short}Correct', s_['by_label'][lb][0])
    eg = out['hard']['eg_tasks']; egr = out['hard']['eg_tasks_resolved']
    m += macro('refEgSentence', (f'The {eg} IdCon-Hard tasks whose v1 references had been settled by a solver that is no longer part of the benchmark were re-settled without it: '
                                 + (f'{egr} with the same label' if egr else 'none could be')
                                 + (f', and {eg - egr} remain' + (' \\textsc{Unassessed}' if eg - egr else '') if eg - egr else '') + '.') if eg else '')
    same = out['hard']['rank'] == out['hard']['corroborated_rank'] and out['hprdx']['rank'] == out['hprdx']['corroborated_rank']
    m += macro('refRankSentence', 'is unchanged on every suite' if same else 'changes only in the order of methods whose PAR-2 differs by less than the bootstrap interval')
    return m


def anc_mean(rows, m, field='par2_ms', sel=None):
    g = collections.defaultdict(list)
    for r in rows:
        if r['method'] == m and r['assessed'] and (sel is None or sel(r)):
            g[r['group_id']].append(r[field])
    return {k: statistics.mean(v) for k, v in g.items()}


def summarize(rows, sel=None):
    out = {}
    for m in ORDER:
        sub = [r for r in rows if r['method'] == m and r['assessed'] and (sel is None or sel(r))]
        if not sub:
            continue
        ok = [r for r in sub if r['correct']]
        a2 = anc_mean(rows, m, 'par2_ms', sel); a10 = anc_mean(rows, m, 'par10w_ms', sel)
        out[m] = dict(assessed=len(sub), correct=len(ok), answered=sum(r['answered'] for r in sub),
                      wrong=sum(r['answered'] and not r['correct'] for r in sub),
                      certified_wrong=sum(r['certified_wrong'] for r in sub),
                      success_ms=statistics.mean(1000 * r['seconds'] for r in ok) if ok else None,
                      par2_ms=statistics.mean(a2.values()), par10w_ms=statistics.mean(a10.values()),
                      ancestors=len(a2),
                      by_label={lb: [sum(r['correct'] for r in sub if r['reference'] == lb),
                                     sum(1 for r in sub if r['reference'] == lb)] for lb in LABELS})
    return out


def rank_probability(rows, methods, sel, strat, draws=10000, seed=20261127):
    """Ancestor bootstrap (stratified by `strat`) of mean PAR-2; P(method has the lowest)."""
    per = {m: anc_mean(rows, m, 'par2_ms', sel) for m in methods}
    per = {m: v for m, v in per.items() if v}
    ids = sorted(set.intersection(*(set(v) for v in per.values())))
    by = collections.defaultdict(list)
    for g in ids:
        by[strat(g)].append(g)
    rng = random.Random(seed)
    wins = collections.Counter()
    best = min(per, key=lambda m: statistics.mean(per[m][g] for g in ids))
    second = min((m for m in per if m != best), key=lambda m: statistics.mean(per[m][g] for g in ids))
    diffs = []
    for _ in range(draws):
        drawn = [rng.choice(v) for _, v in sorted(by.items()) for _ in v]
        means = {m: statistics.mean(per[m][g] for g in drawn) for m in per}
        wins[min(means, key=means.get)] += 1
        diffs.append(means[best] - means[second])
    diffs.sort()
    return dict(prob={m: wins[m] / draws for m in per}, best=best, second=second, ancestors=len(ids),
                diff=statistics.mean(per[best][g] - per[second][g] for g in ids),
                ci95=[diffs[int(.025 * draws)], diffs[int(.975 * draws) - 1]])


def prior_accuracy(refs, manifest, keys):
    return sc.prior_accuracy({t: r for t, r in refs.items() if r['complete']}, manifest, keys)


def labs(c):
    return '/'.join(str(c.get(x, 0)) for x in LABELS)


def stratum_of(tag, r):
    if tag == 'hard':
        return f"{r['entities'] // 1024}k {'plain' if r['variant'] == 'plain' else 'constr.'}"
    if tag == 'hprdx':
        d, k = r['query_set'].split('_')
        return f"{k}{'d' if d == 'dense' else 's'}"
    return 'HPRD'


def main(paper):
    paper = Path(paper)
    (paper / 'tables').mkdir(exist_ok=True)
    an = json.loads((ROOT / 'results/revision_r1/analyses.json').read_text())
    out, macros, data = {}, '', {}
    for tag, study, title in SUITES:
        rows, refs, manifest = sc.score(study)
        rows = [r for r in rows if r['method'] not in LEGACY]
        v1rows, v1refs, _ = sc.score(study, refs_version='v1')
        b10, _, _ = sc.score(study, preds='b10') if study != 'idcon_hprd_x' else ([], None, None)
        data[tag] = (rows, refs, manifest, b10)
        summ = summarize(rows)
        complete = [r for r in refs.values() if r['complete']]
        info = dict(title=title, tasks=len(manifest), ancestors=len({m['group_id'] for m in manifest.values()}),
                    complete=len(complete), unassessed=len(manifest) - len(complete),
                    labels=dict(collections.Counter(r['label'] for r in complete)), methods=summ)
        fm = summ['first_match']
        info['first_wrong_pct'] = 100 * fm['wrong'] / fm['assessed']
        info['first_wrong_of_answered_pct'] = 100 * fm['wrong'] / max(1, fm['answered'])
        fmw = collections.Counter(r['reference'] for r in rows if r['method'] == 'first_match'
                                  and r['assessed'] and r['answered'] and not r['correct'])
        info['first_wrong_by_label'] = dict(fmw)
        info['unknown_share_pct'] = 100 * info['labels'].get('UNKNOWN', 0) / len(complete)
        ex = [m for m in exact(tag) if m in summ]
        sound = [m for m in ex if summ[m]['certified_wrong'] == 0]
        info['unsound'] = [m for m in ex if m not in sound]
        best = min(sound, key=lambda m: summ[m]['par2_ms'])
        info['best'] = best
        info['best_unsolved_pct'] = 100 * (1 - summ[best]['correct'] / summ[best]['assessed'])
        # VBS over the R1 registered sound methods (Glasgow-staged excluded on the v1
        # suites as a post hoc arm; the R2 SAT baseline excluded), and over every
        # sound method that ran (Glasgow-staged and SAT included; R2, Amendment 5)
        def vbs_of(ms):
            per = collections.defaultdict(list)
            for r in rows:
                if r['assessed'] and r['method'] in ms:
                    per[(r['task_id'], r['repeat'])].append(r)
            return per, [k for k, v in per.items() if not any(x['correct'] for x in v)]
        per, uns = vbs_of([m for m in sound if m not in NEW2])
        info['vbs_unsolved'] = len(uns); info['vbs_runs'] = len(per)
        info['vbs_unsolved_pct'] = 100 * len(uns) / len(per)
        info['vbs_unsolved_by_label'] = dict(collections.Counter(per[k][0]['reference'] for k in uns))
        all_sound = [m for m in summ if m != 'first_match' and summ[m]['certified_wrong'] == 0]
        per_a, uns_a = vbs_of(all_sound)
        info['vbs_all_unsolved'] = len(uns_a)
        info['vbs_all_unsolved_pct'] = 100 * len(uns_a) / len(per_a)
        # references: corroboration v1 vs R1
        def negs(rr):
            return [s for r in rr.values() if r['complete'] for s in r['states'].values()
                    if s['status'] == 'UNSAT' and s['engine'] != 'predicate_range']
        info['neg_v1'] = len(negs(v1refs)); info['neg_v1_corroborated'] = sum(bool(s.get('corroborated')) for s in negs(v1refs))
        info['neg_r1'] = len(negs(refs))
        info['neg_r1_corroborated'] = sum(bool(s.get('corroborated') or s.get('corroborated_r1')) for s in negs(refs))
        info['eg_tasks'] = sum(1 for r in refs.values() if r.get('eg_icaf_task'))
        info['eg_tasks_resolved'] = sum(1 for r in refs.values() if r.get('eg_icaf_task') and r['complete'])
        def fully(r):
            return r['complete'] and all(st['status'] != 'UNSAT' or st['engine'] == 'predicate_range'
                                         or st.get('corroborated') or st.get('corroborated_r1')
                                         for st in r['states'].values())
        good = {t for t, r in refs.items() if fully(r)}
        info['corroborated_tasks'] = len(good)
        csum = summarize(rows, sel=lambda r: r['task_id'] in good)
        info['corroborated_summary'] = csum
        info['rank'] = sorted(sound, key=lambda m: summ[m]['par2_ms'])
        info['corroborated_rank'] = sorted([m for m in sound if m in csum], key=lambda m: csum[m]['par2_ms'])
        # priors (no search)
        mkeys = {'hard': ['scenario', 'entities', 'construction', 'variant'], 'hprd': ['scenario'],
                 'hprdx': ['scenario', 'query_set']}[tag]
        info['prior_scenario'] = prior_accuracy(refs, manifest, ['scenario'])
        info['prior_meta'] = prior_accuracy(refs, manifest, mkeys)
        lp = an['learned_prior'][study]
        info['prior_learned'] = (lp['correct'], lp['tasks'])
        info['symmetry'] = an['symmetry'][study]
        # strata: PAR-2 and rank probabilities
        strata = sorted({stratum_of(tag, r) for r in rows}, key=lambda s: (len(s), s))
        info['strata'] = {}
        fam = {r['group_id']: r['family'] for r in rows}
        for st in strata:
            sel = (lambda st: lambda r: stratum_of(tag, r) == st)(st)
            ssum = summarize(rows, sel)
            rp = rank_probability(rows, [m for m in sound if m in ssum], sel,
                                  strat=(lambda g: fam[g]) if tag == 'hard' else (lambda g: 0))
            info['strata'][st] = dict(summary={m: dict(par2=v['par2_ms'], correct=v['correct'], assessed=v['assessed'])
                                               for m, v in ssum.items()}, rank=rp)
        # budgets (0.5, 1, 2 s from the 2 s records; 10 s from repeat-0 records + R1 10 s reruns)
        bud = {}
        for m in ORDER:
            sub = [r for r in rows if r['method'] == m and r['assessed']]
            if not sub:
                continue
            bud[m] = {str(b): sum(r['correct'] and r['seconds'] <= b for r in sub) for b in (0.5, 1.0, 2.0)}
            if b10 and m in B10_METHODS and any(r['method'] == m for r in b10):
                r0 = {r['task_id']: r for r in sub if r['repeat'] == 0}
                ext = {r['task_id']: r for r in b10 if r['method'] == m and r['assessed']}
                ok10 = sum((r0[t]['correct']) or (t in ext and ext[t]['correct']) for t in r0)
                bud[m]['10.0_rep0'] = ok10; bud[m]['2.0_rep0'] = sum(r0[t]['correct'] for t in r0)
                bud[m]['n_rep0'] = len(r0)
        info['budget'] = bud
        out[tag] = info
        # macros
        p = tag
        macros += macro(f'{p}Tasks', info['tasks']) + macro(f'{p}Ancestors', info['ancestors'])
        macros += macro(f'{p}Complete', info['complete']) + macro(f'{p}Unassessed', info['unassessed'])
        macros += macro(f'{p}FirstWrongPct', fmt(info['first_wrong_pct']))
        macros += macro(f'{p}FirstWrongAnsweredPct', fmt(info['first_wrong_of_answered_pct']))
        macros += macro(f'{p}UnknownSharePct', fmt(info['unknown_share_pct']))
        macros += macro(f'{p}FirstWrongOnUnknown', info['first_wrong_by_label'].get('UNKNOWN', 0))
        macros += macro(f'{p}FirstWrong', fm['wrong']) + macro(f'{p}FirstAnswered', fm['answered'])
        macros += macro(f'{p}FirstAssessed', fm['assessed'])
        macros += macro(f'{p}Best', NAMES[best]) + macro(f'{p}BestUnsolvedPct', fmt(info['best_unsolved_pct']))
        rk = info['rank']
        macros += macro(f'{p}BestPar', f"{summ[rk[0]]['par2_ms']:,.0f}") + macro(f'{p}Second', NAMES[rk[1]])
        macros += macro(f'{p}SecondPar', f"{summ[rk[1]]['par2_ms']:,.0f}")
        most = max(rk, key=lambda x: (summ[x]['correct'], -summ[x]['par2_ms']))
        macros += macro(f'{p}Most', NAMES[most]) + macro(f'{p}MostCorrect', summ[most]['correct'])
        macros += macro(f'{p}VBSUnsolved', info['vbs_unsolved']) + macro(f'{p}VBSUnsolvedPct', fmt(info['vbs_unsolved_pct']))
        macros += macro(f'{p}VBSAllUnsolved', info['vbs_all_unsolved']) + macro(f'{p}VBSAllUnsolvedPct', fmt(info['vbs_all_unsolved_pct']))
        macros += macro(f'{p}NegVone', info['neg_v1']) + macro(f'{p}NegVoneCorroborated', info['neg_v1_corroborated'])
        macros += macro(f'{p}NegRone', info['neg_r1']) + macro(f'{p}NegRoneCorroborated', info['neg_r1_corroborated'])
        macros += macro(f'{p}CorroboratedTasks', info['corroborated_tasks'])
        macros += macro(f'{p}PriorScenario', '%d/%d' % info['prior_scenario'])
        macros += macro(f'{p}PriorMeta', '%d/%d' % info['prior_meta'])
        macros += macro(f'{p}PriorLearned', '%d/%d' % info['prior_learned'])
        macros += macro(f'{p}PriorLearnedPct', fmt(100 * info['prior_learned'][0] / info['prior_learned'][1]))
        sy = info['symmetry']
        macros += macro(f'{p}SymExplained', sy.get('symmetry_explained', 0))
        macros += macro(f'{p}SymUnknown', sy.get('unknown_references', 0))
        for m, s in summ.items():
            macros += macro(f'{p}{key(m)}Correct', s['correct']) + macro(f'{p}{key(m)}Assessed', s['assessed'])
            macros += macro(f'{p}{key(m)}Par', fmt(s['par2_ms'], 0)) + macro(f'{p}{key(m)}Wrong', s['wrong'])
            macros += macro(f'{p}{key(m)}ParTen', fmt(s['par10w_ms'], 0))
        for m, b in bud.items():
            if '10.0_rep0' in b:
                macros += macro(f'{p}{key(m)}TenS', b['10.0_rep0']) + macro(f'{p}{key(m)}TwoSRepZero', b['2.0_rep0'])
        nrep = [b['n_rep0'] for b in bud.values() if 'n_rep0' in b]
        if nrep:
            macros += macro(f'{p}RepZeroN', nrep[0])
    if an.get('counts'):
        for k, v in an['counts'].items():
            s, kind = k.split('|'); t = {'idcon_hprd': 'hprd', 'idcon_hprd_x': 'hprdx'}[s]
            kk = 'Full' if kind == 'full_labels' else 'Space'
            macros += macro(f'{t}Count{kk}Queries', v['queries']) + macro(f'{t}Count{kk}Multi', v['more_than_one'])
            macros += macro(f'{t}Count{kk}Thousand', v['at_least_1000']) + macro(f'{t}Count{kk}Unique', v['unique'])
            macros += macro(f'{t}Count{kk}Timeouts', v['timeouts'])
    if an.get('overhead'):
        o = an['overhead']['summary']
        for k, v in o.items():
            macros += macro('ovh' + ''.join(w.capitalize() for w in k.split('_')), fmt(v['median_ms'], 0))

    macros += extra_macros(out, data)
    write_tables(paper, out, data, an)
    import r2_tables  # revision R2: new suites, disclosures, sensitivity, independent check
    r2_tables.write(paper, out, an)
    (paper / 'results_macros_data.tex').write_text(macros)
    (paper / 'analysis_summary.json').write_text(json.dumps(out, indent=1, default=str))
    print('TABLES WRITTEN')


def write_tables(paper, out, data, an):
    T = lambda name, lines: (paper / 'tables' / f'{name}.tex').write_text('\n'.join(lines) + '\n')
    tags = [t for t, _, _ in SUITES]
    # ---- main table
    L = [r'\begin{table*}[t]',
         r'\caption{Main results under the 2\,s end-to-end budget (two repeats per task). Correct: outcome equals the reference. '
         r'Wrong: answered but different from the reference; for a certified answer this is a soundness failure (none occurred). '
         r'PAR-2: ancestor-equal mean, 4\,s for an unanswered or wrong run; best certified method per suite in bold. '
         r'PAR-10w charges a wrong answer 20\,s instead (it differs from PAR-2 only for uncertified methods). '
         r'$^\ast$added in stage~2; $^\ddagger$SAT encoding solved by CaDiCaL, added in stage~3; $^\dagger$post hoc arm on Hard and HPRD. '
         r'Priors predict labels without search, leave one ancestor out, counted per run.}',
         r'\label{tab:main}', r'\centering\small\setlength{\tabcolsep}{4.5pt}', r'\begin{tabular}{l rrr rrr rrr}', r'\toprule',
         ' & ' + ' & '.join(r'\multicolumn{3}{c}{%s (%s runs)}' % (out[t]['title'], f"{out[t]['methods']['lad_state']['assessed']:,}") for t in tags) + r'\\',
         r'\cmidrule(lr){2-4}\cmidrule(lr){5-7}\cmidrule(lr){8-10}',
         'Method' + r' & Correct & Wrong & PAR-2' * 3 + r'\\', r'\midrule']
    for m in ORDER:
        if m == 'first_match':
            L.append(r'\midrule')
        cells = []
        for t in tags:
            s = out[t]['methods'].get(m)
            if not s:
                cells += ['--'] * 3; continue
            par = fmt(s['par2_ms'], 0)
            if m == out[t]['best']:
                par = r'\textbf{' + par + '}'
            if m == 'first_match':
                par += ' / ' + fmt(s['par10w_ms'], 0)
            cells += [f"{s['correct']:,}", f"{s['wrong']:,}", par]
        name = NAMES[m] + (r'$^\ast$' if m in NEW else '') + (r'$^\ddagger$' if m in NEW2 else '') + (r'$^\dagger$' if m == 'glasgow_staged' else '')
        L.append(name + (' (PAR-2 / PAR-10w)' if m == 'first_match' else '') + ' & ' + ' & '.join(cells) + r'\\')
    for label, k in (('Metadata prior', 'prior_meta'), ('Learned prior', 'prior_learned')):
        cells = []
        for t in tags:
            c, n = out[t][k]
            cells += [f'{2 * c:,}', f'{2 * (n - c):,}', '--']
        L.append(label + ' & ' + ' & '.join(cells) + r'\\')
    L += [r'\bottomrule', r'\end{tabular}', r'\end{table*}']
    T('main', L)
    # ---- suites table
    st = an['structure']
    S = [r'\begin{table}[t]', r'\caption{IdCon suites. Labels: assessed references as \Sat/\Vio/\Unk/\Emp. Priors predict the label without search '
         r'(leave one ancestor out): majority of the scenario, majority of all metadata, and a gradient-boosted classifier on metadata and observation-table statistics. '
         r'IdCon-HPRD-H is a held-out split whose labels are not public.}',
         r'\label{tab:suites}', r'\centering\footnotesize', r'\setlength{\tabcolsep}{2.5pt}', r'\begin{tabular}{lcccc}', r'\toprule',
         r' & Hard & HPRD & HPRD-X & HPRD-H\\', r'\midrule',
         r'Source & synthetic & \multicolumn{3}{c}{HPRD graph; third-party queries}\\',
         r'Ancestors / tasks & %d / %d & %d / %d & %d / %d & 100 / 200\\' % tuple(x for t in tags for x in (out[t]['ancestors'], out[t]['tasks'])),
         r'Entities & 2,048--8,192 & 9,460 & 9,460 & 9,460\\',
         r'Roles & 48--96 & 16 & 8--32 & 16\\',
         r'Anchors / metric & 0--2 / yes & no / no & no / no & no / no\\',
         r'Unary domains & no & yes & yes & yes\\',
         r'Assessed refs & %d & %d & %d & hidden\\' % tuple(out[t]['complete'] for t in tags),
         r'Labels & %s & %s & %s & hidden\\' % tuple(labs(collections.Counter(out[t]['labels'])) for t in tags),
         r'Scenario prior & %d/%d & %d/%d & %d/%d & --\\' % tuple(x for t in tags for x in out[t]['prior_scenario']),
         r'Metadata prior & %d/%d & %d/%d & %d/%d & --\\' % tuple(x for t in tags for x in out[t]['prior_meta']),
         r'Learned prior & %d/%d & %d/%d & %d/%d & --\\' % tuple(x for t in tags for x in out[t]['prior_learned']),
         r'\bottomrule', r'\end{tabular}', r'\end{table}']
    T('suites', S)
    # ---- structure table
    cols = [('idcon_hard|plain', 'Hard plain'), ('idcon_hard|constrained', 'Hard constr.'),
            ('idcon_hprd|idcon_hprd', 'HPRD'), ('idcon_hprd_x|idcon_hprd_x', 'HPRD-X')]
    R = [r'\begin{table}[t]', r'\caption{Structural statistics (medians over ancestors; for Hard the degree CV range over the six family medians in brackets). '
         r'Candidate fraction: share of host entities that pass the degree filter and, where present, the unary domain of a non-anchored role.}',
         r'\label{tab:repr}', r'\centering\footnotesize', r'\setlength{\tabcolsep}{3pt}', r'\begin{tabular}{lrrrr}', r'\toprule',
         ' & ' + ' & '.join(c for _, c in cols) + r'\\', r'\midrule']
    def cell(k, f, d):
        v = st[k][f]
        return f'{v:,.{d}f}'
    R.append('Host entities & ' + ' & '.join(cell(k, 'n', 0) for k, _ in cols) + r'\\')
    R.append('Mean degree & ' + ' & '.join(cell(k, 'mean_degree', 1) for k, _ in cols) + r'\\')
    R.append('Degree CV & ' + ' & '.join(cell(k, 'cv', 2) + (' [%.2f--%.2f]' % tuple(st[k]['cv_family_range']) if 'hard' in k else '') for k, _ in cols) + r'\\')
    R.append('Clustering & ' + ' & '.join(cell(k, 'clustering', 3) for k, _ in cols) + r'\\')
    R.append('Pattern edges / role & ' + ' & '.join(cell(k, 'edges_per_role', 2) for k, _ in cols) + r'\\')
    R.append('Candidate fraction & ' + ' & '.join(cell(k, 'candidate', 3) for k, _ in cols) + r'\\')
    R += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
    T('repr', R)
    # ---- labels table (Hard and HPRD-X)
    B = [r'\begin{table}[t]', r'\caption{Correct runs by reference label, S/V/U/E for \Sat/\Vio/\Unk/\Emp{} (assessed runs per label in brackets). \Unk{} needs witnesses only; '
         r'\Sat{}, \Vio{} and \Emp{} need an exhausted counterexample or existence search.}', r'\label{tab:labels}',
         r'\centering\footnotesize', r'\setlength{\tabcolsep}{2.4pt}', r'\begin{tabular}{lrrrr rrr}', r'\toprule']
    hs, xs = out['hard']['methods'], out['hprdx']['methods']
    B.append(r' & \multicolumn{4}{c}{IdCon-Hard} & \multicolumn{3}{c}{IdCon-HPRD-X}\\')
    B.append(r'\cmidrule(lr){2-5}\cmidrule(lr){6-8}')
    xl = [lb for lb in LABELS if xs['lad_state']['by_label'][lb][1]]
    B.append('Method & ' + ' & '.join('%s (%d)' % (lb[0], hs['lad_state']['by_label'][lb][1]) for lb in LABELS)
             + ' & ' + ' & '.join('%s (%d)' % (lb[0], xs['lad_state']['by_label'][lb][1]) for lb in xl) + r'\\')
    B.append(r'\midrule')
    for m in ORDER:
        if m == 'first_match':
            B.append(r'\midrule')
        c1 = [str(hs[m]['by_label'][lb][0]) for lb in LABELS] if m in hs else ['--'] * 4
        c2 = [str(xs[m]['by_label'][lb][0]) for lb in xl] if m in xs else ['--'] * len(xl)
        B.append(show(m, 'hard') + ' & ' + ' & '.join(c1 + c2) + r'\\')
    B += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
    T('labels', B)
    # ---- budget table
    U = [r'\begin{table}[t]', r'\caption{Correct runs within 0.5, 1 and 2\,s (read off the recorded end-to-end times of both repeats), '
         r'and within 10\,s for repeat~0 (2\,s record if answered, otherwise the stage-2 rerun with a 10\,s budget; methods in that run only).}',
         r'\label{tab:budget}', r'\centering\footnotesize', r'\setlength{\tabcolsep}{1.9pt}', r'\begin{tabular}{lrrrr rrrr}', r'\toprule',
         r' & \multicolumn{4}{c}{IdCon-Hard} & \multicolumn{4}{c}{IdCon-HPRD}\\', r'\cmidrule(lr){2-5}\cmidrule(lr){6-9}',
         r'Method & 0.5\,s & 1\,s & 2\,s & 10\,s$^{0}$ & 0.5\,s & 1\,s & 2\,s & 10\,s$^{0}$\\', r'\midrule']
    for m in ORDER:
        if m == 'first_match':
            U.append(r'\midrule')
        cells = []
        for t in ('hard', 'hprd'):
            b = out[t]['budget'].get(m)
            if not b:
                cells += ['--'] * 4; continue
            cells += [str(b['0.5']), str(b['1.0']), str(b['2.0'])]
            cells.append(f"{b['10.0_rep0']}/{b['n_rep0']}" if '10.0_rep0' in b else '--')
        U.append(show(m, 'hard') + ' & ' + ' & '.join(cells) + r'\\')
    U += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
    T('budget', U)
    # ---- strata table with rank probabilities (appendix)
    for t in ('hard', 'hprdx'):
        strata = list(out[t]['strata'])
        A = [r'\begin{table*}[t]', r'\caption{%s by stratum: ancestor-equal PAR-2 in ms (correct runs) and, last row, the bootstrap probability that the best certified method has the lowest PAR-2 '
             r'with the 95\%% interval of its difference to the runner-up (10,000 ancestor resamples%s). Best certified method in bold; '
             r'$^{\circ}$the interval includes 0, so the best and second-best methods are not distinguishable. P(best) is the share of resamples in which the method is best, '
             r'a stability measure rather than a probability of being best.}' % (out[t]['title'], ', stratified by family; 12 ancestors per stratum, 2 per family' if t == 'hard' else ''),
             r'\label{tab:strata-%s}' % t, r'\centering\scriptsize\setlength{\tabcolsep}{2.5pt}', r'\begin{tabular}{l' + 'r' * len(strata) + '}', r'\toprule',
             'Method & ' + ' & '.join(strata) + r'\\', r'\midrule']
        for m in ORDER:
            cells = []
            for s in strata:
                v = out[t]['strata'][s]['summary'].get(m)
                if not v:
                    cells.append('--'); continue
                txt = f"{v['par2']:,.0f} ({v['correct']})"
                cells.append(r'\textbf{' + txt + '}' if out[t]['strata'][s]['rank']['best'] == m else txt)
            A.append(show(m, t) + ' & ' + ' & '.join(cells) + r'\\')
        A.append(r'\midrule')
        rks = [out[t]['strata'][s]['rank'] for s in strata]
        A.append(r'P(best) & ' + ' & '.join('%s %.2f%s' % (NAMES[rk['best']], rk['prob'][rk['best']],
                                                         r'$^{\circ}$' if rk['ci95'][0] <= 0 <= rk['ci95'][1] else '') for rk in rks) + r'\\')
        A.append(r'$\Delta$ to 2nd, 95\% CI & ' + ' & '.join('[%s, %s]' % (fmt(rk['ci95'][0], 0), fmt(rk['ci95'][1], 0)) for rk in rks) + r'\\')
        A += [r'\bottomrule', r'\end{tabular}', r'\end{table*}']
        T(f'strata_{t}', A)
    # ---- scenario table (Hard)
    rows, refs, manifest, _ = data['hard']
    sc_list = ['decoy_v', 'decoy_u', 'decoy_s', 'focal_v', 'mixed', 'background', 'perturbed']
    C = [r'\begin{table}[t]', r'\caption{IdCon-Hard by scenario: assessed references (\Sat/\Vio/\Unk/\Emp) and first-match errors among assessed runs. '
         r'\textsf{decoy\_s} is a predicate-range control (Amendment~1).}', r'\label{tab:scenario}', r'\centering\footnotesize',
         r'\begin{tabular}{lrr}', r'\toprule', r'Scenario & Labels & First-match wrong\\', r'\midrule']
    for s in sc_list:
        comp = [r for t2, r in refs.items() if r['complete'] and manifest[t2]['scenario'] == s]
        fm = [r for r in rows if r['method'] == 'first_match' and r['scenario'] == s and r['assessed']]
        w = sum(r['answered'] and not r['correct'] for r in fm)
        C.append(f"\\textsf{{{s.replace('_', chr(92) + '_')}}} & {labs(collections.Counter(r['label'] for r in comp))} & {w}/{len(fm)}\\\\")
    C += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
    T('scenario', C)
    # ---- family table (Hard)
    fams = sorted({r['family'] for r in rows})
    short = {'articulation_modules': 'Artic.', 'erdos': 'ER', 'geometric': 'Geom.', 'preferential': 'PA', 'regular': 'Reg.', 'small_world': 'SW'}
    sound = [m for m in exact('hard') if out['hard']['methods'][m]['certified_wrong'] == 0]
    V = {(m, f): statistics.mean(anc_mean(rows, m, sel=lambda r, f=f: r['family'] == f).values()) for m in ORDER for f in fams}
    F = [r'\begin{table}[t]', r'\caption{IdCon-Hard ancestor-equal PAR-2 (ms) by graph family (12 ancestors each). Best certified method per family in bold.}',
         r'\label{tab:family}', r'\centering\footnotesize', r'\setlength{\tabcolsep}{3pt}', r'\begin{tabular}{l' + 'r' * len(fams) + '}', r'\toprule',
         'Method & ' + ' & '.join(short[f] for f in fams) + r'\\', r'\midrule']
    for m in ORDER:
        if m == 'first_match':
            F.append(r'\midrule')
        cells = []
        for f in fams:
            b = min(sound, key=lambda x: V[x, f])
            txt = f'{V[m, f]:,.0f}'
            cells.append(r'\textbf{' + txt + '}' if m == b else txt)
        F.append(show(m, 'hard') + ' & ' + ' & '.join(cells) + r'\\')
    F += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
    T('family', F)
    # ---- reference table (appendix)
    G = [r'\begin{table}[t]', r'\caption{Reference quality. Non-trivial negative states (not excluded by the observation tables) and how many a second engine confirms, '
         r'after stage~1 and after the stage-2 re-check; ancestor-equal PAR-2 (ms) on all assessed references and on references whose every non-trivial negative is confirmed.}',
         r'\label{tab:refs}', r'\centering\footnotesize', r'\setlength{\tabcolsep}{3pt}', r'\begin{tabular}{lrrrrrr}', r'\toprule',
         r' & \multicolumn{2}{c}{Hard} & \multicolumn{2}{c}{HPRD} & \multicolumn{2}{c}{HPRD-X}\\', r'\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}',
         r' & all & confirmed & all & confirmed & all & confirmed\\', r'\midrule']
    G.append('Negatives, stage 1 & ' + ' & '.join((f"{out[t]['neg_v1']} & {out[t]['neg_v1_corroborated']}" if t != 'hprdx' else '-- & --') for t in tags) + r'\\')
    G.append('Negatives, stage 2 & ' + ' & '.join(f"{out[t]['neg_r1']} & {out[t]['neg_r1_corroborated']}" for t in tags) + r'\\')
    G.append('Tasks & ' + ' & '.join(f"{out[t]['complete']} & {out[t]['corroborated_tasks']}" for t in tags) + r'\\')
    G.append(r'\midrule')
    for m in ORDER:
        cells = []
        for t in tags:
            a = out[t]['methods'].get(m); c = out[t]['corroborated_summary'].get(m)
            cells += [fmt(a['par2_ms'], 0) if a else '--', fmt(c['par2_ms'], 0) if c else '--']
        G.append(show(m, 'hard') + ' & ' + ' & '.join(cells) + r'\\')
    G += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
    T('refs', G)


if __name__ == '__main__':
    main(sys.argv[1])
