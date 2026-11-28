"""Exercise the packaged native method on one frozen, referenced input."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "experiment"
sys.path.insert(0, str(ROOT / "src"))


def main():
    from structural_adapter import diagnose_tables

    manifest = json.loads((ROOT / "data/processed/lad_sv_confirmation/manifest.json").read_text(encoding="utf8"))
    task = next(item for item in manifest if item["scenario"] == "all_s")
    identity = json.loads((ROOT / task["identity_file"]).read_text(encoding="utf8"))
    observed = json.loads((ROOT / task["tables_file"]).read_text(encoding="utf8"))
    references = (
        json.loads(line)
        for line in (ROOT / "data/protected/lad_sv_confirmation/references.jsonl").read_text(encoding="utf8").splitlines()
    )
    reference = next(row for row in references if row["task_id"] == task["task_id"])
    answer = diagnose_tables(
        identity, {int(role): values for role, values in observed["role_states"].items()},
        observed["global_state"], timeout=10.0,
    )
    assert reference["complete"] and answer["certificate"], answer
    assert answer["label"] == reference["reference_label"], (answer, reference)
    print("PASS:", task["task_id"], answer["label"])


if __name__ == "__main__":
    main()
