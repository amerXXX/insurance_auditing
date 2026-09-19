# Hospital 2 pipeline, part 1/7 — run in numeric order in the same session
# (each part depends on variables defined by the ones before it), or via
# ../main.py which runs every hospital_* folder and combines their outputs.

## Scope and AI-assistance disclosure
#
# Scope: this pipeline audits Hospital 2 against master_services_agreement.md. That
# agreement is the hardest of the four in this exercise to read mechanically: it is
# executed as a deed, it states "No tables are used in this instrument", and clause 1.4
# warns that "The rates for individual Services are not gathered into a single schedule.
# Each rate appears in the Article in which the relevant Service is described, and the
# Articles are not ordered by clinical speciality." Every rate, unit basis, daily cap,
# premium, uplift, discount and bundle is therefore embedded in prose, spread across
# thirteen "Contracted Services (N Group)" Articles that are interleaved with unrelated
# boilerplate Articles (Notices, Audit Rights, Confidentiality, Force Majeure, ...).
#
# AI assistance: Claude was used to enumerate the provision types present in the prose,
# write and verify the clause parsers, and port the reusable matching/pricing/aggregation
# logic from the Hospital 1, 4 and 5 pipelines. The contract interpretations and the
# extraction-completeness assertions are recorded in the decision log at the end of
# 07_aggregation_output.py.
#
# Hospital 2 has no labelled development set (only Hospital 1 does), so there is no
# evaluation-against-labels step here -- Hospital 1's dev-set metrics stand as the
# calibration evidence for this shared method.

from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
import re
import difflib
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
    REPO_ROOT / "invoices" / "hospital_2_invoices.csv",
    parse_dates=["invoice_date"],
)
line_items = pd.read_csv(
    REPO_ROOT / "invoices" / "hospital_2_line_items.csv",
    parse_dates=["service_date"],
)
print(f"Loaded {len(invoices)} invoices, {len(line_items)} line items")
