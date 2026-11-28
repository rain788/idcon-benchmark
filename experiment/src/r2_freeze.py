"""Revision R2: add the SHA-256 of every new frozen record to
results/records_sha256.json. Entries already present are never changed (the
script stops if any of them no longer matches)."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / 'results/records_sha256.json'
PATTERNS = [
    'results/revision_r2/design.json', 'results/revision_r2/amendment_*.json',
    'results/revision_r2/pairs*.json',
    'results/revision_r2/idcheck_sample.json', 'results/revision_r2/idcheck_part*.json',
    'results/revision_r2/idcheck.w*.jsonl', 'results/revision_r2/analyses_r2.json',
    'results/revision_r2/overhead_hard.json', 'results/revision_r2/overhead_hard.jsonl',
    'results/revision_r2/witness_replay_r2.json', 'results/revision_r2/idcheck_pre_a6_part0.json',
    'results/idcon_*/predictions.r2*.jsonl', 'results/idcon_*/predictions.b60*.jsonl',
    'results/idcon_*/predictions.r2calib*.jsonl',
    'results/idcon_hard_x/predictions*.jsonl', 'results/idcon_cite/predictions*.jsonl',
    'data/processed/idcon_hard_x/manifest.json', 'data/processed/idcon_hard_x/input_hashes.json',
    'data/processed/idcon_hard_x/ancestors.json',
    'data/processed/idcon_cite/manifest.json', 'data/processed/idcon_cite/input_hashes.json',
    'data/processed/idcon_cite/ancestors.json', 'data/processed/idcon_cite/source_hashes.json',
    'data/processed/idcon_hard_h/commitment.json',
    'data/protected/idcon_hard_x/references*.jsonl', 'data/protected/idcon_hard_x/construction_maps.json',
    'data/protected/idcon_cite/references*.jsonl', 'data/protected/idcon_cite/construction_maps.json',
    'data/processed/idcon_cite/generation_report.json',
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    reg = json.loads(REG.read_text())
    for rel, d in reg.items():
        assert sha(ROOT / rel) == d, f'frozen record changed: {rel}'
    added = 0
    for pat in PATTERNS:
        for p in sorted(ROOT.glob(pat)):
            rel = str(p.relative_to(ROOT))
            if rel not in reg:
                reg[rel] = sha(p)
                added += 1
    REG.write_text(json.dumps(dict(sorted(reg.items())), indent=1) + '\n')
    print(f'{added} records added; {len(reg)} in total')


if __name__ == '__main__':
    main()
