"""Rebuild Figures 2 and 3 of the IdCon paper  from the scored records.

Usage (repository root):  python paper/make_figures.py
Writes paper/figures/fig2_results.pdf and paper/figures/fig3_strata.pdf.
"""
import collections
import statistics
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mp
import matplotlib.ticker as mt
import numpy as np
from matplotlib.colors import LogNorm

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'experiment' / 'src'))
import score_idcon as sc  # noqa: E402
import analysis_tables as at  # noqa: E402

plt.rcParams.update({'font.size': 8, 'axes.labelsize': 8, 'axes.titlesize': 8, 'legend.fontsize': 7,
                     'xtick.labelsize': 7, 'ytick.labelsize': 7, 'axes.spines.top': False,
                     'axes.spines.right': False, 'legend.frameon': False, 'pdf.fonttype': 42,
                     'axes.titlelocation': 'left', 'xtick.direction': 'out', 'ytick.direction': 'out'})
NAMES = dict(at.NAMES)
NAMES['glasgow_staged'] = 'Glasgow-staged'
EXACT = ['lad_state', 'glasgow', 'glasgow_staged', 'whole_cp', 'traditional_cp', 'enum_glasgow', 'enum_nx', 'asp_cautious',
         'sat_cadical']
# Okabe-Ito based categorical colours; tool baselines dashed, Glasgow-staged dotted
COL = {'lad_state': '#0072B2', 'glasgow': '#009E73', 'glasgow_staged': '#009E73', 'whole_cp': '#CC79A7',
       'traditional_cp': '#999999', 'enum_glasgow': '#E69F00', 'enum_nx': '#56B4E9', 'asp_cautious': '#000000',
       'sat_cadical': '#7F3C8D', 'first_match': '#D55E00'}
LS = {'glasgow_staged': ':', 'enum_glasgow': '--', 'enum_nx': '--', 'asp_cautious': '--', 'traditional_cp': '-.',
      'sat_cadical': '--'}


def rows_of(study, preds='main'):
    r, _, _ = sc.score(study, preds=preds)
    return [x for x in r if x['method'] not in at.LEGACY]


def cactus(ax, rows, exts, methods, title, horizon, rerun_edges=()):
    """Repeat-0 tasks: time of the 2 s run if correct, else of the first longer
    rerun (10 s, then 60 s) that answered correctly; each curve ends at the
    longest budget at which that method was run."""
    for m in methods:
        sub = {r['task_id']: r for r in rows if r['method'] == m and r['assessed'] and r['repeat'] == 0}
        if not sub:
            continue
        t = []
        end = 2000
        for budget, ext_rows in exts:
            if any(r['method'] == m for r in ext_rows):
                end = budget
        for tid, r in sub.items():
            if r['correct']:
                t.append(1000 * r['seconds'])
                continue
            for budget, ext_rows in exts:
                hit = [x for x in ext_rows if x['method'] == m and x['task_id'] == tid and x['assessed'] and x['correct']]
                if hit:
                    t.append(1000 * hit[0]['seconds'])
                    break
        t = np.sort(t); y = np.arange(1, len(t) + 1) / len(sub)
        ax.step(np.r_[t, end], np.r_[y, y[-1] if len(y) else 0], where='post', color=COL[m],
                ls=LS.get(m, '-'), lw=1.1, label=NAMES[m])
    for e in (2000,) + tuple(rerun_edges):
        ax.axvline(e, color='#bbbbbb', lw=.6, zorder=0)
    ax.set_xscale('log'); ax.set_xlim(10, horizon * 1.05); ax.set_ylim(0, 1.02)
    ticks = [10, 100, 1000, 10000, 60000] if horizon > 10000 else ([10, 100, 1000, 10000] if horizon > 2000 else [10, 100, 1000, 2000])
    names = {10: '10', 100: '100', 1000: '1k', 2000: '2k', 10000: '10k', 60000: '60k'}
    ax.xaxis.set_major_locator(mt.FixedLocator(ticks))
    ax.xaxis.set_major_formatter(mt.FixedFormatter([names[x] for x in ticks]))
    ax.xaxis.set_minor_formatter(mt.NullFormatter())
    ax.set_xlabel('end-to-end time (ms)')
    ax.set_title(title)


def firstmatch(ax, suites):
    labels, parts = [], []
    for name, rows in suites:
        sub = [r for r in rows if r['method'] == 'first_match' and r['assessed']]
        c = sum(r['correct'] for r in sub)
        wu = sum(r['answered'] and not r['correct'] and r['reference'] == 'UNKNOWN' for r in sub)
        wo = sum(r['answered'] and not r['correct'] and r['reference'] != 'UNKNOWN' for r in sub)
        assert wo == 0, 'first-match wrong on a non-UNKNOWN reference'
        labels.append(name)
        parts.append((c / len(sub), wu / len(sub), (len(sub) - c - wu) / len(sub)))
    parts = np.array(parts); y = np.arange(len(labels))[::-1]; left = np.zeros(len(labels))
    for k, (lab, col) in enumerate([('correct', '#c8c8c8'), ('wrong (all on “Unknown” references)', COL['first_match']), ('no answer', '#ffffff')]):
        ax.barh(y, parts[:, k], left=left, color=col, edgecolor='#555555', lw=.5, label=lab, height=.6)
        for yi, l, v in zip(y, left, parts[:, k]):
            if k == 1 and v > 0:
                ax.text(l + v / 2, yi, f'{100 * v:.0f}%', ha='center', va='center', color='white', fontsize=7)
        left += parts[:, k]
    ax.set_yticks(y); ax.set_yticklabels(labels); ax.set_xlim(0, 1)
    ax.set_xlabel('fraction of assessed runs'); ax.set_title('First-match answers')


def sig2(v):
    r = float(f'{v:.2g}')
    return f'{r / 1000:.1f}k' if r >= 1000 else f'{r:.0f}'


def main():
    hard, hprd, hprdx = rows_of('idcon_hard'), rows_of('idcon_hprd'), rows_of('idcon_hprd_x')
    hardx, cite = rows_of('idcon_hard_x'), rows_of('idcon_cite')
    out = HERE / 'figures'
    fig, axes = plt.subplots(1, 4, figsize=(7.2, 2.35))
    M = EXACT + ['first_match']
    cactus(axes[0], hard, [(10000, rows_of('idcon_hard', 'b10')), (60000, rows_of('idcon_hard', 'b60'))], M,
           'IdCon-Hard', 60000, (10000, 60000))
    cactus(axes[1], hardx, [(10000, rows_of('idcon_hard_x', 'b10')), (60000, rows_of('idcon_hard_x', 'b60'))], M,
           'IdCon-Hard-X', 60000, (10000, 60000))
    cactus(axes[2], hprdx, [], M, 'IdCon-HPRD-X', 2000)
    cactus(axes[3], cite, [(10000, rows_of('idcon_cite', 'b10'))], M, 'IdCon-Cite', 10000, (10000,))
    axes[0].set_ylabel('fraction answered correctly')
    for ax in axes[1:]:
        ax.set_yticklabels([])
    for ax, l in zip(axes, 'abcd'):
        ax.text(-0.06, 1.07, l, transform=ax.transAxes, fontweight='bold', fontsize=9, ha='right')
    seen = {}
    for ax in axes:
        for h, lab in zip(*ax.get_legend_handles_labels()):
            seen.setdefault(lab, h)
    fig.legend(list(seen.values()), list(seen), loc='lower center', bbox_to_anchor=(0.5, -0.02), ncol=10, fontsize=7,
               handlelength=1.8, columnspacing=0.9)
    fig.tight_layout(w_pad=0.6, rect=(0, 0.13, 1, 1))
    fig.savefig(out / 'fig2_results.pdf', bbox_inches='tight')
    fig.savefig(Path('/tmp/idcon_fig2.png'), dpi=200, bbox_inches='tight')
    plt.close(fig)

    cols, labels = [], []
    for n in (2048, 4096, 8192):
        for v in ('plain', 'constrained'):
            cols.append(('hard', lambda r, n=n, v=v: r['entities'] == n and r['variant'] == v))
            labels.append(f'{n // 1024}k\n{"plain" if v == "plain" else "constr."}')
    cols.append(('hprd', lambda r: True)); labels.append('HPRD\n16')
    for k in ('8', '16', '24', '32'):
        for d in ('dense', 'sparse'):
            cols.append(('hprdx', lambda r, k=k, d=d: r['query_set'] == f'{d}_{k}')); labels.append(f'X {k}{d[0]}')
    import json
    summ = json.loads((HERE / 'analysis_summary.json').read_text())
    keys = [('hard', f'{n // 1024}k {"plain" if v == "plain" else "constr."}') for n in (2048, 4096, 8192) for v in ('plain', 'constrained')]
    keys += [('hprd', 'HPRD')] + [('hprdx', f'{k}{d[0]}') for k in ('8', '16', '24', '32') for d in ('dense', 'sparse')]
    nsig = []
    for t, k in keys:
        rk = summ[t]['strata'].get(k, {}).get('rank')
        nsig.append(bool(rk) and rk['ci95'][0] <= 0 <= rk['ci95'][1])
    R = {'hard': hard, 'hprd': hprd, 'hprdx': hprdx}
    M = np.full((len(EXACT), len(cols)), np.nan)
    for i, m in enumerate(EXACT):
        for j, (s, sel) in enumerate(cols):
            anc = collections.defaultdict(list)
            for r in R[s]:
                if r['method'] == m and r['assessed'] and sel(r):
                    anc[r['group_id']].append(r['par2_ms'])
            if anc:
                M[i, j] = statistics.mean(statistics.mean(x) for x in anc.values())
    fig, ax = plt.subplots(figsize=(7.2, 2.3))
    im = ax.imshow(M, cmap='viridis_r', norm=LogNorm(vmin=30, vmax=4000), aspect='auto')
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if not np.isnan(M[i, j]):
                ax.text(j, i, sig2(M[i, j]), ha='center', va='center', fontsize=7,
                        color='white' if M[i, j] > 300 else 'black')
    for j, (s, _) in enumerate(cols):
        reg = np.array([np.nan if at.posthoc(m, s) else 0 for m in EXACT]) + M[:, j]
        i = np.nanargmin(reg)
        ax.add_patch(mp.Rectangle((j - .5, i - .5), 1, 1, fill=False, ec='#D55E00', lw=1.4,
                                  ls='--' if nsig[j] else '-'))
    ax.set_xticks(range(len(cols))); ax.set_xticklabels(labels, fontsize=7)
    ax.set_yticks(range(len(EXACT))); ax.set_yticklabels([NAMES[m] for m in EXACT], fontsize=7)
    for x in (5.5, 6.5):
        ax.axvline(x, color='white', lw=2)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=.045, pad=.02)
    cb.set_label('PAR-2 (ms, log scale)', fontsize=7)
    cb.ax.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(out / 'fig3_strata.pdf', bbox_inches='tight')
    fig.savefig(Path('/tmp/idcon_fig3.png'), dpi=200, bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    main()
