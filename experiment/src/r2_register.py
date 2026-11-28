"""Write the revision R2 design record and Amendment 5 (run once, before any R2
run on a released or new suite). The record is pushed to the public repository
and released (GitHub release -> Zenodo) before the orchestrator starts, so its
time is fixed by third parties, not by this machine's clock."""
import datetime
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/revision_r2'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    assert not (OUT / 'design.json').exists(), 'already registered'
    OUT.mkdir(parents=True, exist_ok=True)
    import clingo, networkx, ortools, numpy  # noqa: E401
    tools = ROOT / 'third_party/build'
    src = ['hard_benchmark.py', 'submission_data.py', 'external_cite.py', 'external_hprd.py', 'external_hprd_x.py',
           'sat_baseline.py', 'r2_runs.py', 'r2_register.py', 'lad_baseline.py', 'glasgow_baseline.py',
           'revision_baselines.py', 'comparison_baselines.py']
    design = dict(
        study='revision_r2',
        time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        stage=('registered after the R2 pilots (seeds 777002-777005, instances outside every released or new '
               'suite) and before any R2 run on a released suite, before generating the new suites, before '
               'any R2 reference computation and before any R2 scoring'),
        why=('responses to an independent review of the R1 manuscript: headroom claims (budget extension, '
             'harder tier), shortcut and composition analyses, reference independence, overhead, coverage '
             '(real hosts with real labels), a generic SAT baseline, and a synthetic held-out split'),
        new_suites=dict(
            idcon_hard_x=dict(generator='hard_benchmark.generate', seed=202611280201, tiers='16384 entities, 128 roles',
                              density=1, families='six (as IdCon-Hard)',
                              cells='forest+plain and induced+constrained (12 ancestors)',
                              scenarios=['decoy_v', 'decoy_u', 'focal_v', 'mixed', 'background', 'perturbed'],
                              tasks=72, note='decoy_s left out (decided by the observation tables; Amendment 1)'),
            idcon_hard_h=dict(generator='as idcon_hard_x', seed=202611280301, tasks=72,
                              release=('held out: inputs, construction maps and references stay with the '
                                       'authors; manifest hashes, input hashes and the SHA-256 of the reference '
                                       'file are published (commitment); no method is run on it in R2')),
            idcon_cite=dict(builder='external_cite.py', seed=202611280101,
                            hosts='Cora (2,708 vertices, 7 labels) and PubMed (19,717 vertices, 3 labels) from '
                                  'github.com/kimiyoung/planetoid commit af6abf4 (MIT); not redistributed',
                            queries='random-walk induced subgraphs, k in {8,16,24}, dense (avg degree >= 3) and '
                                    'sparse, 8 per set and host (96 ancestors)',
                            observation_rule='as IdCon-HPRD (spec_true / spec_wrong)', tasks=192)),
        methods=dict(
            new=dict(sat_cadical=('sat_baseline.py: identity space encoded to CNF (independent/cnf_encoding.py), '
                                  'two-query reduction with selector unit clauses, one CaDiCaL 2.1.3 process per '
                                  'query, killed at the budget; witnesses replayed')),
            idcon_cite=['lad_state', 'glasgow', 'glasgow_staged', 'whole_cp', 'traditional_cp', 'first_match',
                        'enum_glasgow', 'enum_nx', 'asp_cautious', 'sat_cadical'],
            idcon_hard_x=['lad_state', 'glasgow', 'glasgow_staged', 'whole_cp', 'enum_glasgow', 'first_match',
                          'sat_cadical'],
            idcon_hard_x_note=('Trad-CP, Enum-VF2 and ASP-cautious are not run on IdCon-Hard-X: on IdCon-Hard '
                               'they answer 214, 14 and 15 of 1,008 runs at 2 s; compute is spent on longer '
                               'budgets instead'),
            released_suites='sat_cadical on IdCon-Hard, IdCon-HPRD and IdCon-HPRD-X (2 s, two repeats)'),
        runs=dict(
            calib=('50 seeded IdCon-Hard tasks x {LAD, Glasgow --staged}, repeat 0, 2 s, on the R2 machine; '
                   'compared with the frozen v1 records (speed ratio, outcome agreement)'),
            hardx_2s='IdCon-Hard-X, 7 methods, 2 s, one repeat',
            hardx_10s='IdCon-Hard-X, 7 methods, 10 s, one repeat',
            hardx_60s='IdCon-Hard-X, LAD / Glasgow --staged / SAT pairs unanswered at 10 s, 60 s',
            cite_2s='IdCon-Cite, 10 methods, 2 s, two repeats',
            cite_10s='IdCon-Cite, pairs unanswered in a 2 s repeat for LAD, Glasgow --staged, CP-SAT, ASP-cautious, SAT; 10 s, repeat 0',
            hard_60s=('IdCon-Hard repeat 0: LAD and Glasgow --staged on every pair not answered correctly at '
                      '2 s or 10 s; CP-SAT on every task that no method answered at 2 s or 10 s; 60 s'),
            sat_released='sat_cadical on IdCon-Hard, IdCon-HPRD, IdCon-HPRD-X, 2 s, two repeats',
            overhead=('first query (exists T in {S,U,V}) of LAD2025 and Glasgow --staged on 48 IdCon-Hard tasks '
                      '(8 per tier x variant): total, solver process wall time, outside-solver time, '
                      'solver-reported time'),
            process_model=('two executors pinned to one vCPU each (taskset); jobs on 16,384-entity hosts never run '
                           'concurrently with each other (memory); timed jobs first, then pairs, extended '
                           'budgets, then untimed jobs (references, independent check), then the overhead job alone'),
            machine=dict(platform=platform.platform(), python=sys.version.split()[0],
                         note='2 vCPU / 8 GB cloud VM, not the R1 VM; see calib',
                         ortools=ortools.__version__, clingo=clingo.__version__, networkx=networkx.__version__,
                         numpy=numpy.__version__,
                         binaries={p.name: sha(p) for p in sorted(tools.iterdir()) if p.is_file()} |
                                  {'lad2025': sha(tools / 'lad2025/lad2025')},
                         glasgow_commit='01ef6caec4dbf0ef0206689d769f0b67aacd38b5 (rebuilt with gcc 13.3)',
                         cadical='rel-2.1.3 (f13d744)', drat_trim='2e3b2dc',
                         stack='unlimited (LAD2025 segfaults on 16,384-entity hosts with 8 MB)')),
        references=dict(
            new_suites=('hard_benchmark.reference_task (LAD2025 30 s per state, Glasgow corroboration 30 s; '
                        'LAD timeouts fall back to Glasgow 60 s then CP-SAT 60 s; construction-map replay for '
                        'synthetic suites); the independent check below is the second engine'),
            independent_check=dict(
                code='experiment/independent/ (cnf_encoding.py, idcheck.py): imports nothing from experiment/src',
                procedure=('per task, the three exact-state queries T(y)=S,U,V: witness search on an '
                           'arc-consistent CNF, witness replayed against the raw JSON; a negative answer is '
                           're-derived on the CNF without arc consistency with a DRAT proof checked by drat-trim; '
                           'no-search negatives only for an empty domain (anchors, unary domains, degree bound, '
                           'tables) or no entity in the queried state; 600 s per solve, 1,200 s per proof check'),
                sample=('IdCon-Hard: every task with a negative state not confirmed by a second engine in R1, '
                        'plus 8 seeded tasks per tier x variant stratum (48); IdCon-HPRD-X: every task '
                        'ASP-cautious did not answer; IdCon-Cite and IdCon-Hard-X: every task'),
                pilot='10 pilot tasks (seeds 777004, 777005): 10 agreements with reference_task')),
        analyses=dict(
            registered_r2=[
                'IdCon-Hard VBS at 2 s, 10 s and 60 s (repeat 0) over the sound methods, with and without '
                'Glasgow --staged; LAD at 10 s and 60 s',
                'completion curves to 60 s (IdCon-Hard, IdCon-Hard-X)',
                'IdCon-Hard-X and IdCon-Cite main tables (correct / wrong / unanswered, ancestor-equal PAR-2 '
                'at the run budget, correct by label), with the three no-search priors',
                'sat_cadical rows for every suite',
                'independent-check agreement table (agree / disagree / unresolved, by suite and why)',
                'overhead decomposition on IdCon-Hard',
                'calibration of the R2 machine against v1 records'],
            amendment_5_posthoc=[
                'disclosure of the two solvers removed by Amendment 4 (EG-ICAF, LAD-SV: the authors\' own, '
                'unpublished methods): frozen-record results on IdCon-Hard and IdCon-HPRD and their effect on '
                'the VBS (appendix; not ranked)',
                'IdCon-Hard sensitivity: without the decoy_s control (432 tasks) and without the tasks whose label '
                'the tables decide up to non-emptiness (non-perturbed, two states excluded by the tables)',
                'embedding multiplicity corrected for query automorphisms (IdCon-HPRD)',
                'stratum comparisons: differences whose bootstrap interval includes 0 reported as not '
                'distinguishable',
                'runtime errors per method and suite',
                'overlap of the three priors\' errors'],
            note=('the R1 primary analysis (504 IdCon-Hard tasks, decoy_s included) stays the primary analysis; '
                  'the sensitivity analyses are post hoc')),
        data_handling=dict(
            history_rewrite=('2026-11-27: repository history rewritten with git filter-repo to remove '
                             'experiment/data/raw/hprd_sun_luo/ (HPRD graph, Sun-Luo queries); old->new commit map '
                             'in results/revision_r2/commit_map.txt; frozen records unchanged (records_sha256.json)')),
        code_sha256={f: sha(ROOT / 'src' / f) for f in src} |
                    {f'independent/{f}': sha(ROOT / 'independent' / f) for f in ('cnf_encoding.py', 'idcheck.py')})
    (OUT / 'design.json').write_text(json.dumps(design, indent=1))
    print('REGISTERED', sha(OUT / 'design.json'))


if __name__ == '__main__':
    main()
