"""Paper tables and macros for revision R2 (called by analysis_tables.main)."""
import collections
import hashlib
import json
from pathlib import Path

import r2_analyses as r2a

ROOT = r2a.ROOT
LABELS = r2a.LABELS
NAMES = {'lad_state': 'LAD', 'glasgow': 'Glasgow', 'glasgow_staged': 'Glasgow-staged',
         'whole_cp': 'CP-SAT', 'traditional_cp': 'Trad-CP', 'enum_glasgow': 'Enum-Glasgow',
         'enum_nx': 'Enum-VF2', 'asp_cautious': 'ASP-cautious', 'sat_cadical': 'SAT',
         'first_match': 'First-match', 'eg_icaf': 'EG-ICAF', 'lad_sv_early': 'LAD-SV'}
ORDER = ['lad_state', 'glasgow', 'glasgow_staged', 'whole_cp', 'traditional_cp',
         'enum_glasgow', 'enum_nx', 'asp_cautious', 'sat_cadical', 'first_match']


DIGITS = {'0': 'Zero', '1': 'One', '2': 'Two', '3': 'Three', '4': 'Four', '5': 'Five', '6': 'Six',
          '7': 'Seven', '8': 'Eight', '9': 'Nine'}


def macro(name, value):
    name = ''.join(DIGITS.get(c, c) for c in name if c.isalnum())  # TeX control words: letters only
    return f'\\newcommand{{\\{name}}}{{{value}}}\n'


def fmt(x, d=0):
    return '--' if x is None else f'{x:,.{d}f}'


def labs(c):
    return '/'.join(str(c.get(x, 0)) for x in LABELS)


def show(m):
    return NAMES[m] + (r'$^\ast$' if m in ('enum_glasgow', 'enum_nx', 'asp_cautious') else '') + \
        (r'$^\ddagger$' if m == 'sat_cadical' else '')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(paper, out, an):
    paper = Path(paper)
    T = lambda name, lines: (paper / 'tables' / f'{name}.tex').write_text('\n'.join(lines) + '\n')
    g = r2a.gather()
    m = ''
    new = g['new']
    hx, ct = new.get('idcon_hard_x'), new.get('idcon_cite')
    # ---------------------------------------------------------------- suites table (all suites)
    hh = ROOT / 'data/processed/idcon_hard_h'
    hh_tasks = len(json.loads((hh / 'manifest.json').read_text())) if (hh / 'manifest.json').exists() else 72
    def pr(x):
        return '--' if not x else '%d/%d' % tuple(x)
    tags = ['hard', 'hprd', 'hprdx']
    S = [r'\begin{table*}[t]',
         r'\caption{IdCon suites. Labels: assessed references as \Sat/\Vio/\Unk/\Emp. Priors predict the label without search '
         r'(leave one ancestor out): majority of the scenario, majority of all metadata, and a gradient-boosted classifier on metadata and '
         r'observation-table statistics. IdCon-HPRD-H and IdCon-Hard-H are held-out splits whose labels are not public; IdCon-Hard-H inputs are also withheld '
         r'(hashes published). $^\ddagger$: added in stage~3.}',
         r'\label{tab:suites}', r'\centering\footnotesize', r'\setlength{\tabcolsep}{3.5pt}', r'\begin{tabular}{lccccccc}', r'\toprule',
         r' & Hard & Hard-X$^\ddagger$ & HPRD & HPRD-X & Cite$^\ddagger$ & HPRD-H & Hard-H$^\ddagger$\\', r'\midrule',
         r'Source & synthetic & synthetic & \multicolumn{2}{c}{HPRD; third-party queries} & Cora, PubMed & HPRD & synthetic\\',
         r'Ancestors / tasks & %d / %d & %d / %d & %d / %d & %d / %d & %d / %d & 100 / 200 & 12 / %d\\' % (
             out['hard']['ancestors'], out['hard']['tasks'], hx['ancestors'], hx['tasks'], out['hprd']['ancestors'], out['hprd']['tasks'],
             out['hprdx']['ancestors'], out['hprdx']['tasks'], ct['ancestors'], ct['tasks'], hh_tasks),
         r'Entities & 2,048--8,192 & 16,384 & 9,460 & 9,460 & 2,708; 19,717 & 9,460 & 16,384\\',
         r'Roles & 48--96 & 128 & 16 & 8--32 & 8--24 & 16 & 128\\',
         r'Anchors / metric & 0--2 / yes & 0--2 / yes & no / no & no / no & no / no & no / no & 0--2 / yes\\',
         r'Unary domains & no & no & yes & yes & yes & yes & no\\',
         r'Assessed refs & %d & %d & %d & %d & %d & hidden & hidden\\' % (
             out['hard']['complete'], hx['complete'], out['hprd']['complete'], out['hprdx']['complete'], ct['complete']),
         r'Labels & %s & %s & %s & %s & %s & hidden & hidden\\' % (
             labs(out['hard']['labels']), labs(hx['labels']), labs(out['hprd']['labels']), labs(out['hprdx']['labels']), labs(ct['labels'])),
         r'Scenario prior & %s & %s & %s & %s & %s & -- & --\\' % (pr(out['hard']['prior_scenario']), pr(hx['prior_scenario']),
                                                                 pr(out['hprd']['prior_scenario']), pr(out['hprdx']['prior_scenario']), pr(ct['prior_scenario'])),
         r'Metadata prior & %s & %s & %s & %s & %s & -- & --\\' % (pr(out['hard']['prior_meta']), pr(hx['prior_meta']),
                                                                 pr(out['hprd']['prior_meta']), pr(out['hprdx']['prior_meta']), pr(ct['prior_meta'])),
         r'Learned prior & %s & %s & %s & %s & %s & -- & --\\' % (pr(out['hard']['prior_learned']), pr(hx['prior_learned']),
                                                                pr(out['hprd']['prior_learned']), pr(out['hprdx']['prior_learned']), pr(ct['prior_learned'])),
         r'\bottomrule', r'\end{tabular}', r'\end{table*}']
    T('suites', S)
    m += macro('totalTasksRtwo', f"{sum(out[t]['tasks'] for t in tags) + hx['tasks'] + ct['tasks']:,}")
    m += macro('totalAncestorsRtwo', sum(out[t]['ancestors'] for t in tags) + hx['ancestors'] + ct['ancestors'])
    for p, e in (('hardx', hx), ('cite', ct)):
        m += macro(f'{p}Tasks', e['tasks']) + macro(f'{p}Ancestors', e['ancestors']) + macro(f'{p}Complete', e['complete'])
        m += macro(f'{p}Unassessed', e['tasks'] - e['complete']) + macro(f'{p}Labels', labs(e['labels']))
        m += macro(f'{p}PriorScenario', pr(e['prior_scenario'])) + macro(f'{p}PriorMeta', pr(e['prior_meta']))
        m += macro(f'{p}PriorLearned', pr(e['prior_learned']))
        for secs, v in e['ladder_vbs_unsolved'].items():
            m += macro(f'{p}VBSUnsolved' + {2: 'Two', 10: 'Ten', 60: 'Sixty'}[int(secs)], v)
        for meth, lad in e['ladder'].items():
            k = NAMES[meth].replace('-', '')
            for secs, v in lad.items():
                m += macro(f'{p}{k}' + {2: 'Two', 10: 'Ten', 60: 'Sixty'}[int(secs)], v)
        for secs in (2, 10, 60):  # best single sound method within each budget
            cand = {meth: lad.get(secs, lad.get(str(secs))) for meth, lad in e['ladder'].items() if meth != 'first_match'}
            cand = {k2: v for k2, v in cand.items() if v is not None}
            if cand:
                bm = max(cand, key=cand.get)
                w = {2: 'Two', 10: 'Ten', 60: 'Sixty'}[secs]
                m += macro(f'{p}BestSingle{w}', NAMES[bm]) + macro(f'{p}BestSingle{w}N', cand[bm])
        summ2 = e['main']['summary']
        snd = [x for x in summ2 if x != 'first_match' and summ2[x]['certified_wrong'] == 0]
        best = min(snd, key=lambda x: summ2[x]['par2_ms'])
        m += macro(f'{p}Best', NAMES[best]) + macro(f'{p}BestPar', fmt(summ2[best]['par2_ms']))
        m += macro(f'{p}CertWrong', sum(summ2[x]['certified_wrong'] for x in summ2 if x != 'first_match'))
        fm = summ2.get('first_match')
        if fm:
            m += macro(f'{p}FirstWrong', fm['wrong']) + macro(f'{p}FirstAnswered', fm['assessed'] - fm['unanswered'])
    m += macro('hardhTasks', hh_tasks)
    wr2 = ROOT / 'results/revision_r2/witness_replay_r2.json'
    if wr2.exists():
        wr = json.loads(wr2.read_text())
        legacy = {'eg_icaf', 'lad_sv_early'}
        tot = sum(c for st in wr.values() for k, c in st['by_method'].items() if k.split('|')[0] not in legacy and k.endswith('|True'))
        bad = sum(c for st in wr.values() for k, c in st['by_method'].items() if k.endswith('|False'))
        assert bad == 0, 'witness replay failures'
        m += macro('witnessTotalRtwo', f'{tot:,}')
    for study, p in (('idcon_hard_x', 'hardx'), ('idcon_cite', 'cite')):
        neg = cor = 0
        for f in sorted((ROOT / 'data/protected' / study).glob('references*.jsonl')):
            for line in f.read_text().splitlines():
                r = json.loads(line)
                if not r['complete']:
                    continue
                for st in r['states'].values():
                    if st['status'] == 'UNSAT' and st['engine'] != 'predicate_range':
                        neg += 1
                        cor += bool(st.get('corroborated'))
        m += macro(f'{p}Neg', neg) + macro(f'{p}NegCorroborated', cor)
    commit = ROOT / 'data/processed/idcon_hard_h/commitment.json'
    if commit.exists():
        m += macro('hardhCommit', json.loads(commit.read_text())['references_sha256'][:12])
    # ---------------------------------------------------------------- new suites table
    N = [r'\begin{table}[t]',
         r'\caption{Stage-3 suites (repeat~0, one run per task and budget on IdCon-Hard-X; two repeats at 2\,s on IdCon-Cite). '
         r'Correct runs within 2, 10 and 60\,s (a run unanswered at a budget is rerun at the next for the methods listed in the design record; -- not rerun). '
         r'VBS: tasks that no sound method answers within the budget. No certified answer contradicts a reference.}',
         r'\label{tab:newsuites}', r'\centering\footnotesize', r'\setlength{\tabcolsep}{2.6pt}', r'\begin{tabular}{lrrr rrr}', r'\toprule',
         r' & \multicolumn{3}{c}{IdCon-Hard-X (%d tasks)} & \multicolumn{3}{c}{IdCon-Cite (%d tasks)}\\' % (hx['complete'], ct['complete']),
         r'\cmidrule(lr){2-4}\cmidrule(lr){5-7}', r'Method & 2\,s & 10\,s & 60\,s & 2\,s$^{2}$ & PAR-2 & 10\,s\\', r'\midrule']
    rer_x = set(hx['b60']['summary']) if 'b60' in hx else set()
    rer_c = set(ct['b10']['summary']) if 'b10' in ct else set()
    for meth in ORDER:
        if meth not in hx['ladder'] and meth not in ct['main']['summary']:
            continue
        if meth == 'first_match':
            N.append(r'\midrule')
        a = hx['ladder'].get(meth)
        cx = [str(a[2]) if a else '--', str(a[10]) if a else '--', str(a[60]) if a and meth in rer_x else '--']
        s2 = ct['main']['summary'].get(meth)
        lad = ct['ladder'].get(meth)
        cc = [f"{s2['correct']}" if s2 else '--', fmt(s2['par2_ms']) if s2 else '--',
              str(lad[10]) if lad and meth in rer_c else '--']
        N.append(show(meth) + ' & ' + ' & '.join(cx + cc) + r'\\')
    N.append(r'\midrule')
    N.append(r'VBS unsolved & %d & %d & %d & %d & -- & %d\\' % (hx['ladder_vbs_unsolved'][2], hx['ladder_vbs_unsolved'][10],
                                                             hx['ladder_vbs_unsolved'][60], ct['main']['vbs']['unsolved'],
                                                             ct['ladder_vbs_unsolved'][10]))
    N += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
    T('newsuites', N)
    m += macro('citeRuns', ct['main']['runs'] // len(ct['main']['summary']))
    m += macro('citeVBSUnsolvedRuns', ct['main']['vbs']['unsolved'])
    # ---------------------------------------------------------------- IdCon-Hard budgets (60 s)
    b = g['budget_hard']
    for k, v in b['lad'].items():
        m += macro('hardLadRep' + {2: 'Two', 10: 'Ten', 60: 'Sixty'}[int(k)], v)
    for k, v in b['glasgow_staged'].items():
        m += macro('hardGSRep' + {2: 'Two', 10: 'Ten', 60: 'Sixty'}[int(k)], v)
    for k, v in b['vbs_all_unsolved'].items():
        m += macro('hardVBSAllUnsolved' + {2: 'Two', 10: 'Ten', 60: 'Sixty'}[int(k)], v)
    for k, v in b['vbs_r1_unsolved'].items():
        m += macro('hardVBSROneUnsolved' + {2: 'Two', 10: 'Ten', 60: 'Sixty'}[int(k)], v)
    m += macro('hardSixtyRuns', b['b60_runs'])
    tex = {'SATISFIES': r'\Sat{}', 'VIOLATES': r'\Vio{}', 'UNKNOWN': r'\Unk{}', 'EMPTY': r'\Emp{}'}
    m += macro('hardVBSSixtyLabels', ', '.join(f'{v} {tex[k]}' for k, v in sorted(
        b['vbs_all_unsolved_60_by_label'].items(), key=lambda kv: -kv[1])))
    # ---------------------------------------------------------------- legacy disclosure
    leg = g['legacy']
    L = [r'\begin{table}[t]',
         r'\caption{The authors\textquotesingle{} own unpublished solvers EG-ICAF and LAD-SV, run in stage~1 and not part of the benchmark (Amendment~4), '
         r'from the frozen stage-1 records scored against the final references. They are not ranked; they show that the headroom left by the benchmarked methods is not a lower bound '
         r'on what exact methods can do. VBS unsolved: runs that no sound method answers, over the stage-1 and stage-2 methods / with EG-ICAF / with both.}',
         r'\label{tab:legacy}', r'\centering\footnotesize', r'\setlength{\tabcolsep}{3pt}', r'\begin{tabular}{lrrr rrr}', r'\toprule',
         r' & \multicolumn{3}{c}{IdCon-Hard (1,008 runs)} & \multicolumn{3}{c}{IdCon-HPRD (400 runs)}\\', r'\cmidrule(lr){2-4}\cmidrule(lr){5-7}',
         r'Method & Correct & Wrong & PAR-2 & Correct & Wrong & PAR-2\\', r'\midrule']
    for meth in ('lad_state', 'eg_icaf', 'lad_sv_early'):
        cells = []
        for st in ('idcon_hard', 'idcon_hprd'):
            v = leg[st]['lad'] if meth == 'lad_state' else leg[st]['methods'].get(meth)
            cells += [str(v['correct']), str(v['wrong']), fmt(v['par2_ms'])] if v else ['--'] * 3
        L.append(NAMES[meth] + ' & ' + ' & '.join(cells) + r'\\')
    L.append(r'\midrule')
    L.append(r'VBS unsolved & \multicolumn{3}{c}{%d / %d / %d} & \multicolumn{3}{c}{%d / %d / %d}\\' % (
        leg['idcon_hard']['vbs_r1']['unsolved'], leg['idcon_hard']['vbs_with_eg']['unsolved'], leg['idcon_hard']['vbs_with_both']['unsolved'],
        leg['idcon_hprd']['vbs_r1']['unsolved'], leg['idcon_hprd']['vbs_with_eg']['unsolved'], leg['idcon_hprd']['vbs_with_both']['unsolved']))
    L += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
    T('legacy', L)
    eg = leg['idcon_hard']['methods']['eg_icaf']; sv = leg['idcon_hard']['methods']['lad_sv_early']
    m += macro('legEgCorrect', eg['correct']) + macro('legEgPar', fmt(eg['par2_ms'])) + macro('legEgUnans', eg['unanswered'])
    m += macro('legSvCorrect', sv['correct']) + macro('legSvPar', fmt(sv['par2_ms']))
    m += macro('legVBSEg', leg['idcon_hard']['vbs_with_eg']['unsolved']) + macro('legVBSBoth', leg['idcon_hard']['vbs_with_both']['unsolved'])
    m += macro('legEgUnsolvedPct', fmt(100 * (1 - eg['correct'] / eg['assessed']), 1))
    # ---------------------------------------------------------------- sensitivity (Amendment 5)
    sen = g['sensitivity']
    meths = [x for x in ORDER if x in sen['all']]
    Z = [r'\begin{table}[t]',
         r'\caption{IdCon-Hard sensitivity (Amendment~5, post hoc): correct runs and ancestor-equal PAR-2 (ms) on all 504 tasks (registered analysis), '
         r'without the \textsf{decoy\_s} control (432), and without the %d tasks whose label the observation tables decide up to the existence of an identity '
         r'(two states excluded by the tables in a scenario whose construction embedding is admissible; %d of them \textsf{decoy\_s}).}' % (
             sen['table_decided_tasks'], sen['decided_by_scenario'].get('decoy_s', 0)),
         r'\label{tab:sensitivity}', r'\centering\footnotesize', r'\setlength{\tabcolsep}{2.4pt}', r'\begin{tabular}{lrr rr rr}', r'\toprule',
         r' & \multicolumn{2}{c}{All (1,008 runs)} & \multicolumn{2}{c}{No \textsf{decoy\_s} (%d)} & \multicolumn{2}{c}{Non-trivial (%d)}\\' % (
             sen['no_decoy_s']['lad_state']['assessed'], sen['nontrivial']['lad_state']['assessed']),
         r'\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}', r'Method & Correct & PAR-2 & Correct & PAR-2 & Correct & PAR-2\\', r'\midrule']
    for meth in meths:
        if meth == 'first_match':
            Z.append(r'\midrule')
        cells = []
        for k in ('all', 'no_decoy_s', 'nontrivial'):
            v = sen[k][meth]
            cells += [str(v['correct']), fmt(v['par2_ms'])]
        Z.append(show(meth) + ' & ' + ' & '.join(cells) + r'\\')
    Z += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
    T('sensitivity', Z)
    m += macro('sensDecided', sen['table_decided_tasks']) + macro('sensDecidedDecoyS', sen['decided_by_scenario'].get('decoy_s', 0))
    m += macro('sensDecidedPct', fmt(100 * sen['table_decided_tasks'] / 504, 1))
    def rank(k):
        snd = [x for x in sen[k] if x != 'first_match']
        return [NAMES[x] for x in sorted(snd, key=lambda x: sen[k][x]['par2_ms'])]
    same = rank('all')[:3] == rank('no_decoy_s')[:3] == rank('nontrivial')[:3]
    m += macro('sensRankSentence', ('the order of the three fastest sound methods (' + ', '.join(rank('all')[:3]) + ') is the same on all three subsets')
               if same else ('the three fastest sound methods are ' + ', '.join(rank('all')[:3]) + ' on all tasks and ' + ', '.join(rank('nontrivial')[:3]) + ' on the non-trivial subset'))
    # ---------------------------------------------------------------- independent check
    idc = g.get('idcheck')
    if idc:
        names = {'idcon_hard|unconfirmed_negative': 'Hard, unconfirmed negative', 'idcon_hard|stratified_random': 'Hard, stratified random',
                 'idcon_hprd_x|no_asp_answer': 'HPRD-X, no ASP answer', 'idcon_cite|new_suite': 'Cite, all tasks',
                 'idcon_hard_x|new_suite_sample': 'Hard-X, one per ancestor',
                 'idcon_hard_x|uncorroborated_negative': 'Hard-X, single-engine negative'}
        I = [r'\begin{table}[t]',
             r'\caption{Independent reference check: an encoding written without any benchmark code, solved by CaDiCaL; witnesses replayed against the raw input; '
             r'negatives decided on the unpruned encoding with DRAT proofs verified by drat-trim. Settles: tasks \textsc{Unassessed} in the reference that the check decides. '
             r'Limits: 600\,s per solve and 1,200\,s per proof check (registered) for the first 4 tasks, 120\,s and 300\,s for the rest (Amendment~6); '
             r'Hard-X single-engine negatives: every IdCon-Hard-X task with a negative state that only one reference engine established, not already sampled (Amendment~7).}',
             r'\label{tab:idcheck}', r'\centering\footnotesize', r'\setlength{\tabcolsep}{3pt}', r'\begin{tabular}{lrrrrr}', r'\toprule',
             r'Sample & Tasks & Agree & Disagree & Unresolved & Settles\\', r'\midrule']
        tot = collections.Counter()
        for k in names:
            v = idc['table'].get(k)
            if not v:
                continue
            tot.update(v)
            I.append(f"{names[k]} & {v.get('tasks', 0)} & {v.get('agree', 0)} & {v.get('disagree', 0)} & {v.get('unresolved', 0)} & {v.get('settles_unassessed', 0)}\\\\")
        I.append(r'\midrule')
        I.append(f"Total & {tot['tasks']} & {tot['agree']} & {tot['disagree']} & {tot['unresolved']} & {tot['settles_unassessed']}\\\\")
        I += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
        T('idcheck', I)
        m += macro('idcTasks', tot['tasks']) + macro('idcAgree', tot['agree']) + macro('idcDisagree', tot['disagree'])
        m += macro('idcUnresolved', tot['unresolved']) + macro('idcDecided', tot['agree'] + tot['disagree'] + tot['settles_unassessed'])
        m += macro('idcSettles', tot['settles_unassessed'])
        m += macro('idcDrat', idc['how'].get('drat_verified', 0))
        hu = idc['table'].get('idcon_hard|unconfirmed_negative', {})
        m += macro('idcUnconfAgree', hu.get('agree', 0)) + macro('idcUnconfTasks', hu.get('tasks', 0))
        for key, nm in (('idcon_cite|new_suite', 'idcCite'), ('idcon_hard_x|uncorroborated_negative', 'idcHardxSingle'),
                        ('idcon_hard_x|new_suite_sample', 'idcHardxSample')):
            v = idc['table'].get(key, {})
            m += macro(nm + 'Agree', v.get('agree', 0)) + macro(nm + 'Tasks', v.get('tasks', 0))
            m += macro(nm + 'Unresolved', v.get('unresolved', 0))
        hr = idc['table'].get('idcon_hard|stratified_random', {})
        m += macro('idcRandAgree', hr.get('agree', 0)) + macro('idcRandTasks', hr.get('tasks', 0))
    # ---------------------------------------------------------------- runtime errors
    E = [r'\begin{table}[t]', r'\caption{Runs that ended in a runtime error (scored as unanswered), over all records of each suite. '
         r'Enum-Glasgow errors on IdCon-Hard are processes killed by the operating system for memory (exit $-9$).}',
         r'\label{tab:errors}', r'\centering\footnotesize', r'\setlength{\tabcolsep}{3pt}', r'\begin{tabular}{lrrrrr}', r'\toprule',
         r'Method & Hard & HPRD & HPRD-X & Hard-X & Cite\\', r'\midrule']
    er = g['runtime_errors']
    for meth in ORDER:
        cells = []
        for st in ('idcon_hard', 'idcon_hprd', 'idcon_hprd_x', 'idcon_hard_x', 'idcon_cite'):
            e = er.get(st, {})
            n = e.get('runs', {}).get(meth)
            cells.append('--' if not n else f"{e['errors'].get(meth, 0)}/{n}")
        E.append(show(meth) + ' & ' + ' & '.join(cells) + r'\\')
    E += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
    T('errors', E)
    # ---------------------------------------------------------------- misc macros
    po = g['prior_overlap_hard']
    m += macro('priorWrongAllThree', po['wrong_all_three']) + macro('priorWrongLearned', po['wrong_learned'])
    ca = g['calibration']
    m += macro('calibRuns', ca['runs']) + macro('calibAgree', ca['outcome_agree'])
    m += macro('calibRatio', fmt(ca['median_ratio'], 2) if ca['median_ratio'] else '--') + macro('calibBoth', ca['both_correct'])
    au = g.get('automorphism') or {}
    for st, p in (('idcon_hprd', 'hprd'), ('idcon_hprd_x', 'hprdx')):
        if st in au:
            m += macro(f'{p}AutoOrbitMulti', au[st]['more_than_one_orbit'])
    oh = g.get('overhead_hard')
    if oh:
        for meth, k in (('lad_state', 'Lad'), ('glasgow_staged', 'GS')):
            v = oh[meth]
            m += macro(f'ovhHard{k}Total', fmt(1000 * v['median_total_s'])) + macro(f'ovhHard{k}Solver', fmt(1000 * v['median_solver_wall_s']))
            m += macro(f'ovhHard{k}Outside', fmt(1000 * v['median_outside_solver_s']))
            m += macro(f'ovhHard{k}Reported', fmt(1000 * v['median_solver_reported_s']) if v.get('median_solver_reported_s') is not None else '--')
    (paper / 'results_macros_r2.tex').write_text(m)
    (paper / 'analysis_summary_r2.json').write_text(json.dumps(g, indent=1, default=str))
    return g
