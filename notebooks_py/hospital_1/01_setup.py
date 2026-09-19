# Hospital 1 pipeline, part 1/9 — run in numeric order in the same session
# (each part depends on variables defined by the ones before it), or via
# ../main.py which runs every hospital_* folder and combines their outputs.

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
    REPO_ROOT / "invoices" / "hospital_1_invoices.csv",
    parse_dates=["invoice_date"],
)
line_items = pd.read_csv(
    REPO_ROOT / "invoices" / "hospital_1_line_items.csv",
    parse_dates=["service_date"],
)
print(f"Loaded {len(invoices)} invoices, {len(line_items)} line items")
