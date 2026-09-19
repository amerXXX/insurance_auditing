# Hospital 3 pipeline, part 1/7 — run in numeric order in the same session
# (each part depends on variables defined by the ones before it), or via
# ../main.py which runs every hospital_* folder and combines their outputs.

## Scope and AI-assistance disclosure
#
# Scope: this pipeline audits Hospital 3, whose contract is the one "split across several
# documents" that the exercise brief warns about. Three instruments have to be read
# together (base_agreement.md clause 1.3): the Base Agreement (rules), Appendix B (the
# rate schedule), and Amendment No. 1 (substituted and additional rates). Clause 1.3 also
# fixes the precedence: an amendment prevails over Appendix B, and Appendix B prevails
# over the Base Agreement.
#
# The feature that makes Hospital 3 different from the other four is that its rates are
# time-dependent. Amendment No. 1 takes effect on 1 January 2025 and clause A1.1.2 says it
# applies *by Service Date*, expressly stating that "The date on which an invoice is
# issued is irrelevant for this purpose". Roughly half the line items in the data fall
# either side of that date, so a pipeline that priced everything on one rate table would
# misprice about half the invoices.
#
# AI assistance: Claude was used to read the three documents, cross-check them against one
# another, write the extraction and the date-aware pricing, and port the reusable
# matching/aggregation logic from the Hospital 1, 2, 4 and 5 pipelines. The contract
# interpretations are recorded in the decision log at the end of 07_aggregation_output.py.
#
# Hospital 3 has no labelled development set (only Hospital 1 does), so there is no
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
    REPO_ROOT / "invoices" / "hospital_3_invoices.csv",
    parse_dates=["invoice_date"],
)
line_items = pd.read_csv(
    REPO_ROOT / "invoices" / "hospital_3_line_items.csv",
    parse_dates=["service_date"],
)
print(f"Loaded {len(invoices)} invoices, {len(line_items)} line items")
