"""Write the revision R1 design record and Amendment 4 (run once, before any R1 run).

The record is committed and pushed to the public repository before any R1
inference, reference re-check or scoring, so its time is fixed by GitHub
independently of this machine's clock.
"""
import datetime, hashlib, json, platform, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/revision_r1'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    assert not (OUT / 'design.json').exists(), 'already registered'
    src = ['hard_benchmark.py', 'revision_baselines.py', 'revision_references.py', 'revision_counts.py',
           'revision_validate.py', 'revision_register.py', 'revision_runs.py', 'external_hprd.py', 'external_hprd_x.py',
           'lad_baseline.py', 'glasgow_baseline.py', 'comparison_baselines.py', 'full_benchmark_methods.py',
           'coordination_confirmation_data.py', 'final_confirmation_evidence.py', 'projection_engine.py']
    import clingo, networkx, ortools, numpy, scipy, sklearn
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    design = dict(
        study='revision_r1',
        time=now,
        stage=('registered after implementation of the R1 baselines and their pilot validation on '
               'instances outside every released suite (seed 777001), and before any R1 run on a '
               'released suite, any reference re-check and any scoring of R1 records'),
        scope=dict(
            suites_scored=['idcon_hard', 'idcon_hprd', 'idcon_hprd_x'],
            suite_holdout='idcon_hprd_h (references computed, kept out of the public repository; '
                          'their SHA-256 is published as a commitment)',
            removed_from_paper=['IdCon-Core suite', 'lad_sv_early (LAD-SV)', 'eg_icaf (EG-ICAF)',
                                'SNAP/SUM4Re regressions'],
            removed_note='legacy material of an abandoned, never-submitted method draft; frozen v1 '
                         'records are kept unchanged (git tag v1.0) but are not analysed in R1'),
        methods=dict(
            registered_v1=['lad_state', 'glasgow', 'whole_cp', 'traditional_cp', 'first_match'],
            posthoc_v1=['glasgow_staged'],
            new_r1=['enum_glasgow', 'enum_nx', 'asp_cautious'],
            names={'lad_state': 'LAD', 'glasgow': 'Glasgow', 'glasgow_staged': 'Glasgow-staged',
                   'whole_cp': 'CP-SAT', 'traditional_cp': 'Trad-CP', 'first_match': 'First-match',
                   'enum_glasgow': 'Enum-Glasgow', 'enum_nx': 'Enum-VF2', 'asp_cautious': 'ASP-cautious'},
            glasgow_staged_note='post hoc on idcon_hard/idcon_hprd (v1 Amendment 3, marked with a dagger); '
                                'registered here in advance for idcon_hprd_x and the extended-budget runs'),
        runs=dict(
            R1_main=dict(suites=['idcon_hard (manifest + manifest_focal)', 'idcon_hprd'],
                         methods=['enum_glasgow', 'enum_nx', 'asp_cautious'], budget_s=2.0, repeats=2,
                         schedule='hard_benchmark.run_shard (v1 seed, shuffled task order, '
                                  'randomised method order), prediction tag r1'),
            R1_X=dict(suite='idcon_hprd_x', methods=['lad_state', 'glasgow', 'glasgow_staged', 'whole_cp',
                                                     'traditional_cp', 'first_match', 'enum_glasgow',
                                                     'enum_nx', 'asp_cautious'], budget_s=2.0, repeats=2),
            R1_B10=dict(suites=['idcon_hard', 'idcon_hprd'], budget_s=10.0, repeats=1,
                        methods=['lad_state', 'glasgow_staged', 'whole_cp', 'enum_glasgow',
                                 'glasgow (idcon_hprd only)'],
                        pairs=('every (task, method) pair whose 2 s run returned NO_ANSWER in at least one '
                               'repeat (v1 records for v1 methods, R1_main records for enum_glasgow); '
                               'pairs answered in both 2 s repeats are not rerun'),
                        purpose='does difficulty persist beyond the 2 s budget'),
            R1_overhead=dict(suite='idcon_hprd', what=('fixed per-call cost: time to write the host graph, and '
                             'LAD2025 / Glasgow (default, --staged) on a one-role pattern; 20 calls each')),
            R1_counts=dict(what='hprd_embedding_counts (revision_counts.py)', limit_s=30),
            process_model=('one timing worker pinned to vCPU 0; reference re-check, new-suite references and '
                           'counts on vCPU 1; once that queue is empty a second timing worker continues the '
                           'timing queue on vCPU 1 (two concurrent single-thread processes, as in v1); '
                           'same 2-vCPU VM type as v1 (' + platform.platform() + ')')),
        references=dict(
            hard=('revision_references.recheck: (a) the 114 non-trivial negative states without second-engine '
                  'corroboration in v1 are re-queried with Glasgow --staged (30 s), then CP-SAT (60 s); '
                  '(b) the 3 tasks settled by the EG-ICAF consensus in v1 are re-settled with LAD2025, '
                  'Glasgow --staged and CP-SAT (120 s each, per undetermined state), else UNASSESSED; '
                  'a positive witness against any v1 negative aborts the re-check and is reported'),
            new_suites=('hard_benchmark.reference_task without EG-ICAF: construction-free; LAD2025 30 s per '
                        'state query with Glasgow 30 s corroboration; LAD timeouts fall back to Glasgow 60 s, '
                        'then CP-SAT 60 s; positive witnesses replayed'),
            proof_logging=('assessed, not used: Glasgow --prove rejects labelled inputs ("Proof logging cannot '
                           'yet be used on labelled graphs"), which the unary-domain/metric encoding needs; '
                           'on the smallest plain EMPTY task (unlabelled) Glasgow did not finish in 100 s '
                           'without proof logging (LAD2025 0.12 s)'),
            scoring='R1 tables use R1 references; tasks UNASSESSED after R1 are excluded from every denominator'),
        analyses=dict(
            A1_base_rate='first-match errors by reference label; check that every first-match error is an '
                         'UNKNOWN reference (structural consequence of the definitions)',
            A2_soundness_gate=('leaderboard: methods with any certified wrong outcome are listed separately and '
                               'not ranked by PAR-2; PAR-10 (20 s at the 2 s budget) reported for wrong outcomes'),
            A3_strata_uncertainty=('per stratum (Hard: tier x variant; HPRD; HPRD-X: query size x density) '
                                   'ancestor-level paired bootstrap of PAR-2 (10,000 draws, family-stratified '
                                   'on Hard, seed 20261127) and the probability that each method has the '
                                   'lowest PAR-2'),
            A4_learned_prior=('HistGradientBoostingClassifier (scikit-learn defaults, random_state 0), '
                              'leave-one-ancestor-out, features available without search: manifest metadata '
                              '(family, tier, roles, construction, variant, scenario, generator parameters), '
                              'ancestor statistics (host/pattern edges, components, anchors, metric edges) and '
                              'observation-table statistics (per checked role: counts of S/U/V entities overall '
                              'and among degree-feasible entities; number of checked roles with no S entity; '
                              'global state); reported per suite as correct tasks'),
            A5_automorphisms=('lower bound on UNKNOWN references explained by pattern symmetry: generators of '
                              'Aut(Q) that fix anchors, metric edges and unary domains (pynauty or NetworkX '
                              'GraphMatcher on Q), applied to the construction embedding; a generator that '
                              'changes the state certifies symmetry-induced UNKNOWN'),
            A6_hprd_counts='distribution of embedding counts (full labels and IdCon identity space)',
            A7_overhead='R1_overhead',
            A8_budget_curves='completion curves to 10 s from R1_B10 combined with 2 s records',
            A9_reference_subsets='main table on all assessed references and on references with every '
                                 'non-trivial negative confirmed by a second engine',
            A10_registration_table='each reported analysis classified as v1-registered, v1-post hoc, '
                                   'R1-registered (this record) or R1-post hoc'),
        source_hashes={f: sha(ROOT / 'src' / f) for f in src},
        binary_hashes={'third_party/build/lad2025/lad2025': sha(ROOT / 'third_party/build/lad2025/lad2025'),
                       'third_party/build/glasgow_subgraph_solver': sha(ROOT / 'third_party/build/glasgow_subgraph_solver')},
        glasgow_build=dict(upstream='https://github.com/ciaranm/glasgow-subgraph-solver',
                           commit='01ef6caec4dbf0ef0206689d769f0b67aacd38b5',
                           note='v1 did not record the source commit of its Glasgow binary; 01ef6ca was the '
                                'newest upstream commit when v1 ran. Compiler: ' +
                                subprocess.run(['g++', '--version'], capture_output=True, text=True).stdout.splitlines()[0]),
        manifests={s: sha(ROOT / 'data/processed' / s / 'manifest.json')
                   for s in ('idcon_hard', 'idcon_hprd', 'idcon_hprd_x', 'idcon_hprd_h')},
        manifest_focal=sha(ROOT / 'data/processed/idcon_hard/manifest_focal.json'),
        source_data={s: sha(ROOT / 'data/processed' / s / 'source_hashes.json') for s in ('idcon_hprd_x', 'idcon_hprd_h')},
        pilot=dict(file='results/revision_r1/pilot_validation.jsonl',
                   sha256=sha(OUT / 'pilot_validation.jsonl'),
                   summary='154 pilot tasks; 0 disagreements with exhaustive VF2 reference; 0 replay failures'),
        environment=dict(python=sys.version, platform=platform.platform(), clingo=clingo.__version__,
                         networkx=networkx.__version__, ortools=ortools.__version__,
                         numpy=numpy.__version__, scipy=scipy.__version__, sklearn=sklearn.__version__),
    )
    amendment = dict(
        amendment=4, time=now, study='idcon_hard, idcon_hprd (applies to the paper and the release)',
        reason=('IdCon-Core, LAD-SV and EG-ICAF come from an earlier method draft of the authors that was '
                'abandoned and never submitted. They are removed from the benchmark, the paper and the main '
                'branch. EG-ICAF is also removed as a reference engine (v1 Amendment 2): the 3 IdCon-Hard tasks '
                'whose references rested on its consensus are re-settled without it or become UNASSESSED.'),
        unchanged='all v1 predictions and references (frozen; tag v1.0); records of the removed methods are '
                  'kept in the prediction files but excluded from every R1 analysis',
        registered_before='any R1 run, re-check or scoring (see results/revision_r1/design.json)')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'design.json').write_text(json.dumps(design, indent=1, ensure_ascii=False) + '\n')
    (OUT / 'amendment_4.json').write_text(json.dumps(amendment, indent=1, ensure_ascii=False) + '\n')
    print('REGISTERED', now)


if __name__ == '__main__':
    main()
