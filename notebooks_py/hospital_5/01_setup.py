# Hospital 5 pipeline, part 1/7 — run in numeric order in the same session
# (each part depends on variables defined by the ones before it), or via
# ../main.py which runs every hospital_* folder and combines their outputs.

## Scope and AI-assistance disclosure
#
# Scope: this pipeline audits Hospital 5 against network_reimbursement_agreement.md,
# following the same audit framework built for Hospital 1 and reused for Hospital 4.
# Hospital 5 is the first contract in this exercise whose rates genuinely vary by
# facility and by patient plan tier (Tables 2 and 3), so the pricing engine gains two
# real multiplier stages that were structurally 1x for Hospitals 1 and 4. The
# service-matching vocabulary, the confidence policy and the aggregation logic are
# carried over unchanged.
#
# AI assistance: Claude was used to read the Hospital 5 agreement, re-derive the
# contract-extraction and checks steps against its actual clause/table structure, and
# port the reusable matching/pricing/aggregation logic from the Hospital 1 and 4
# pipelines. The contract interpretations and implementation decisions are recorded in
# the decision log at the end of 07_aggregation_output.py.
#
# Hospital 5 has no labelled development set (only Hospital 1 does), so there is no
# evaluation-against-labels step here -- Hospital 1's dev-set metrics stand as the
# calibration evidence for this shared method.
#
# The rate tables are also supplied as a separate PDF
# (network_reimbursement_agreement_rate_tables.pdf). Its Table 1/2/3 values were
# extracted and compared against the Markdown agreement before this pipeline was
# written: all 84 services agree exactly on base rate, unit basis, daily cap, and all
# three facility and three plan-tier multipliers. The Markdown is therefore parsed as
# the single source of truth and the PDF is treated as a redundant rendering.

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
    REPO_ROOT / "invoices" / "hospital_5_invoices.csv",
    parse_dates=["invoice_date"],
)
line_items = pd.read_csv(
    REPO_ROOT / "invoices" / "hospital_5_line_items.csv",
    parse_dates=["service_date"],
)
print(f"Loaded {len(invoices)} invoices, {len(line_items)} line items")
