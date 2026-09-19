"""Run every hospital's audit pipeline and combine their submissions into one file.

Usage:
    python main.py

Each hospital_N/ folder holds a numbered pipeline (01_setup.py, 02_..., ...,
NN_output.py). This script runs those files in order, in a single shared
namespace per hospital -- exactly like running notebook cells top to bottom,
since each step depends on variables the previous ones defined. The last step
in every hospital's pipeline writes that hospital's own hospital_N/submission.csv.
This script then concatenates every hospital_*/submission.csv it finds into one
combined file at <repo root>/submission.csv (the folder that contains both
notebooks_py/ and insurance_auditing-main/).

To add a new hospital (e.g. hospital_5) once its data/contract exist under
insurance_auditing-main/: create notebooks_py/hospital_5/ with the same
numbered-file pattern, ending with a step that writes hospital_5/submission.csv
in the exact submission_template.csv schema. No changes to this script are
needed -- hospital_* folders are discovered automatically.
"""
from pathlib import Path
import sys
import pandas as pd

NOTEBOOKS_DIR = Path(__file__).resolve().parent
REQUIRED_COLUMNS = [
    "invoice_id", "flagged", "error_category",
    "expected_total_cents", "billed_total_cents", "confidence",
]


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
        per_hospital.append((hospital_dir.name, df))

    combined = pd.concat([df for _, df in per_hospital], ignore_index=True)
    assert combined["invoice_id"].is_unique, "Duplicate invoice_id across hospitals"

    combined_output_path = NOTEBOOKS_DIR.parent / "submission.csv"
    combined.to_csv(combined_output_path, index=False)

    print(f"\n=== Combined {len(combined)} rows from {len(hospital_dirs)} hospitals ===")
    for name, df in per_hospital:
        print(f"  {name}: {len(df)} rows")
    print(f"Wrote {combined_output_path}")


if __name__ == "__main__":
    main()
