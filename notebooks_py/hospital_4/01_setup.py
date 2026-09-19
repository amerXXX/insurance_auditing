# Hospital 4 pipeline, part 1/7 — run in numeric order in the same session
# (each part depends on variables defined by the ones before it), or via
# ../main.py which runs every hospital_* folder and combines their outputs.

## Scope and AI-assistance disclosure
#
# Scope: this notebook develops the Hospital 4 audit pipeline, following the same
# audit/evaluation framework built for Hospital 1 in mainHP_1_final.ipynb. Hospital 4's
# contract (conditional_reimbursement_agreement.md) has a different structure and section
# numbering than Hospital 1's, so the contract-extraction cells are rewritten against
# Hospital 4's actual clauses; the service-matching vocabulary, the pricing-order engine,
# and the aggregation/confidence logic are carried over unchanged, since the underlying
# billing-description abbreviations and the contractual adjustment order (bundle -> facility
# -> plan -> premium/uplift -> discount) are the same across hospitals in this exercise.
#
# AI assistance: Claude was used to read Hospital 1's notebook, port its reusable
# service-matching and pricing/aggregation logic, and re-derive the Hospital-4-specific
# contract-extraction and checks cells from conditional_reimbursement_agreement.md. The
# final contract interpretations, thresholds, and implementation decisions were reviewed by
# the author; see the decision log in 07_aggregation_output.py.
#
# Hospital 4 has no labelled development set (only Hospital 1 does), so there is no
# evaluation-against-labels section here -- the H1 notebook's dev-set metrics stand as the
# calibration evidence for this shared method.

from pathlib import Path
import pandas as pd

def find_repo_root(start: Path = None, marker: str = "invoices") -> Path:
    # Searches from the current working directory AND from this file's own
    # location, so it resolves correctly whether run directly (cwd = the repo)
    # or driven by ../main.py (cwd = wherever main.py was invoked from).
    candidates = []
    start = start or Path.cwd()
    candidates.extend([start, *start.parents])
    here = Path(globals().get("__file__", ".")).resolve().parent
    candidates.extend([here, *here.parents])
    # This file lives at <repo>/notebooks_py/hospital_N/, i.e. two levels below
    # the folder that holds insurance_auditing-main/ as a sibling of notebooks_py/.
    candidates.append(here.parent.parent / "insurance_auditing-main")
    for candidate in candidates:
        if (candidate / marker).is_dir() and (candidate / "contracts").is_dir():
            return candidate.resolve()
    checked = ", ".join(str(c) for c in dict.fromkeys(candidates))
    raise FileNotFoundError(f"Could not find the insurance-auditing repository. Checked: {checked}")

REPO_ROOT = find_repo_root()

invoices = pd.read_csv(
    REPO_ROOT / "invoices" / "hospital_4_invoices.csv",
    parse_dates=["invoice_date"],
)
line_items = pd.read_csv(
    REPO_ROOT / "invoices" / "hospital_4_line_items.csv",
    parse_dates=["service_date"],
)
print(f"Loaded {len(invoices)} invoices, {len(line_items)} line items")
