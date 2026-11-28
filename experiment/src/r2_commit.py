"""Hash commitment for the held-out synthetic split IdCon-Hard-H (revision R2).

Neither the inputs nor the references of IdCon-Hard-H are public: task ids name
the scenario, which predicts the label, so even the manifest stays private. This
script writes the only public file, data/processed/idcon_hard_h/commitment.json,
which commits to
  * the inputs: SHA-256 of the canonical input-hash list (one line per task,
    sorted by task_id: task_id, identity-file SHA-256, tables-file SHA-256);
  * the references: SHA-256 of the canonical label file (one JSON object per
    task, sorted by task_id, keys sorted: complete, label, task_id).
The canonical files themselves are written next to the private references.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / 'data/processed/idcon_hard_h'
PRIV = ROOT / 'data/protected/idcon_hard_h'


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    hashes = json.loads((PUB / 'input_hashes.json').read_text())
    inputs = ''.join(f"{t}\t{h['identity_file']}\t{h['tables_file']}\n" for t, h in sorted(hashes.items())).encode()
    refs = {}
    for p in sorted(PRIV.glob('references.w*.jsonl')) + sorted(PRIV.glob('references.zretry.jsonl')):
        for line in p.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                refs[r['task_id']] = r
    assert set(refs) == set(hashes), (len(refs), len(hashes))
    canon = ''.join(json.dumps({'complete': bool(refs[t].get('complete', True)), 'label': refs[t]['label'],
                                'task_id': t}, sort_keys=True) + '\n' for t in sorted(refs)).encode()
    (PRIV / 'inputs_canonical.tsv').write_bytes(inputs)
    (PRIV / 'references_canonical.jsonl').write_bytes(canon)
    out = {
        'suite': 'idcon_hard_h',
        'tasks': len(hashes),
        'assessed': sum(bool(r.get('complete', True)) for r in refs.values()),
        'seed_registered': 'experiment/results/revision_r2/design.json',
        'inputs_canonical_format': 'one line per task, sorted by task_id: task_id TAB identity-file SHA-256 TAB tables-file SHA-256',
        'inputs_sha256': sha(inputs),
        'references_canonical_format': 'one JSON object per task, sorted by task_id, keys sorted: {"complete", "label", "task_id"}, newline-terminated',
        'references_sha256': sha(canon),
        'note': 'Inputs, manifest and references are kept by the maintainers; send predictions to the corresponding author for scoring.',
    }
    (PUB / 'commitment.json').write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
