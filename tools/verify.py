"""Read-only verification of the IdCon release (v1.2).

1. Checks the SHA-256 of every frozen record (predictions, references, manifests,
   design records, counts, analyses) against experiment/results/records_sha256.json.
2. Checks that every method witness replays (experiment/results/witness_replay.json
   for v1.1 records and experiment/results/revision_r2/witness_replay_r2.json for all
   records including revision R2 have no failure); with --replay it recomputes the
   R2 replay (needs the task inputs).
3. Recomputes every paper table and macro from the records and compares them byte
   for byte with paper/tables and paper/results_macros_data.tex.
   With --analyses it first recomputes results/revision_r1/analyses.json from the
   task inputs (learned prior, symmetry, structure statistics); this needs the
   inputs (README, "Quick start") and takes about ten minutes; with --analyses-r2 it
   recomputes results/revision_r2/analyses_r2.json (also needs the inputs).
The held-out IdCon-HPRD-H and IdCon-Hard-H references are not public and are not
checked here; their commitments are.
No timing is rerun.
"""
import filecmp, hashlib, json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / 'experiment'
sys.path.insert(0, str(EXP / 'src'))
TABLES = ['main', 'suites', 'repr', 'labels', 'budget', 'strata_hard', 'strata_hprdx', 'scenario', 'family', 'refs',
          'newsuites', 'legacy', 'sensitivity', 'idcheck', 'errors']
MACROS = ['results_macros_data.tex', 'results_macros_r2.tex']


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    args = set(sys.argv[1:])
    frozen = json.loads((EXP / 'results/records_sha256.json').read_text())
    for rel, digest in frozen.items():
        assert sha(EXP / rel) == digest, f'hash mismatch: {rel}'
    print(f'records: {len(frozen)} files match their frozen hashes')
    if '--replay' in args:
        subprocess.run([sys.executable, str(EXP / 'src/replay_witnesses.py'), 'idcon_hard', 'idcon_hprd', 'idcon_hprd_x',
                        'idcon_hard_x', 'idcon_cite'], check=True,
                       env={**__import__('os').environ, 'IDCON_REPLAY_OUT': 'results/revision_r2/witness_replay_r2.json'})
    for name in ('results/witness_replay.json', 'results/revision_r2/witness_replay_r2.json'):
        wr = json.loads((EXP / name).read_text())
        assert all(v['failures'] == 0 for v in wr.values()), f'witness replay failures in {name}'
        print(f'witnesses ({name}):', {k: v['witnesses'] for k, v in wr.items()}, 'all replay')
    if '--analyses' in args:
        subprocess.run([sys.executable, str(EXP / 'src/revision_analyses.py')], check=True, cwd=EXP / 'src')
    if '--analyses-r2' in args:
        subprocess.run([sys.executable, str(EXP / 'src/r2_analyses.py'), 'compute'], check=True, cwd=EXP / 'src')
    import analysis_tables
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / 'tables').mkdir()
        analysis_tables.main(tmp)
        bad = [n for n in MACROS + [f'tables/{t}.tex' for t in TABLES]
               if not filecmp.cmp(Path(tmp) / n, ROOT / 'paper' / n, shallow=False)]
        assert not bad, f'recomputed outputs differ from the paper: {bad}'
    print('paper tables and macros: recomputed and identical')
    print('VERIFIED')


if __name__ == '__main__':
    main()
