"""Run every hospital's audit pipeline and combine their submissions into one file.

Usage:
    python main.py

Each hospital_N/ folder holds a numbered pipeline (01_setup.py, 02_..., ...,
NN_output.py). This script runs those files in order, in a single shared
namespace per hospital -- exactly like running notebook cells top to bottom,
since each step depends on variables the previous ones defined. The last step
in every hospital's pipeline writes that hospital's own hospital_N/submission.csv
(every hospital's own file is always written, dev-only ones included).

This script then concatenates every SCORED hospital's submission.csv into one
combined file at <repo root>/submission.csv. A hospital counts as scored unless
insurance_auditing-main/labels/<hospital_N>_labels.csv exists -- a labels file
means it is a development/calibration set (Hospital 1's role in this exercise),
not part of the graded submission. This mirrors the exercise's own design: only
the labelled hospital is for calibration, everything else is scored.

To add a new hospital (e.g. hospital_2) once its data/contract exist under
insurance_auditing-main/: create notebooks_py/hospital_2/ with the same
numbered-file pattern, ending with a step that writes hospital_2/submission.csv
in the exact submission_template.csv schema. No changes to this script are
needed -- hospital_* folders are discovered automatically, and it is included
in the combined file unless a labels file exists for it.
"""
from pathlib import Path
import sys
import pandas as pd

NOTEBOOKS_DIR = Path(__file__).resolve().parent
REPO_ROOT = NOTEBOOKS_DIR.parent
LABELS_DIR = REPO_ROOT / "insurance_auditing-main" / "labels"
REQUIRED_COLUMNS = [
    "invoice_id", "flagged", "error_category",
    "expected_total_cents", "billed_total_cents", "confidence",
]


def is_scored(hospital_name: str) -> bool:
    """A hospital is scored unless it has a labels file (dev/calibration set)."""
    return not (LABELS_DIR / f"{hospital_name}_labels.csv").exists()


def run_hospital(hospital_dir: Path) -> Path:
    """Execute a hospital's numbered pipeline files in order, in one namespace."""
    scripts = sorted(hospital_dir.glob("[0-9][0-9]_*.py"))
    if not scripts:
        raise FileNotFoundError(f"No numbered pipeline files (NN_*.py) found in {hospital_dir}")

    print(f"\n=== {hospital_dir.name} ({len(scripts)} steps) ===")
    namespace: dict = {"__name__": "__main__"}
    for script in scripts:
        print(f"  -> {script.name}")
        namespace["__file__"] = str(script)
        code = compile(script.read_text(encoding="utf-8"), str(script), "exec")
        exec(code, namespace)

    output_path = hospital_dir / "submission.csv"
    if not output_path.exists():
        raise FileNotFoundError(
            f"{hospital_dir.name}'s pipeline finished but did not write {output_path}"
        )
    return output_path


def main() -> None:
    hospital_dirs = sorted(
        p for p in NOTEBOOKS_DIR.iterdir()
        if p.is_dir() and p.name.startswith("hospital_")
    )
    if not hospital_dirs:
        print(f"No hospital_* folders found in {NOTEBOOKS_DIR}.")
        sys.exit(1)

    per_hospital = []
    for hospital_dir in hospital_dirs:
        output_path = run_hospital(hospital_dir)
        df = pd.read_csv(output_path)
        assert df.columns.tolist() == REQUIRED_COLUMNS, (
            f"{hospital_dir.name}/submission.csv has unexpected columns: {df.columns.tolist()}"
        )
        per_hospital.append((hospital_dir.name, df, is_scored(hospital_dir.name)))

    scored = [df for _, df, scored_flag in per_hospital if scored_flag]
    combined = pd.concat(scored, ignore_index=True)
    assert combined["invoice_id"].is_unique, "Duplicate invoice_id across hospitals"

    combined_output_path = REPO_ROOT / "submission.csv"
    combined.to_csv(combined_output_path, index=False)

    n_scored = sum(1 for *_, s in per_hospital if s)
    print(f"\n=== Combined {len(combined)} rows from {n_scored} scored hospital(s) "
          f"(of {len(hospital_dirs)} run) ===")
    for name, df, scored_flag in per_hospital:
        tag = "scored" if scored_flag else "dev/calibration only -- excluded from combined file"
        print(f"  {name}: {len(df)} rows ({tag})")
    print(f"Wrote {combined_output_path}")


if __name__ == "__main__":
    main()
