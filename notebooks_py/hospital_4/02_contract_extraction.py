# Hospital 4 pipeline, part 2/7 — depends on 01_setup.py having run first
# (uses REPO_ROOT, invoices).

## Section 3 -- Base Rates, and clause 2.1 / 2.2 data checks
#
# Clause 2.1: term 1 Jan 2024 -- 31 Dec 2025. Clause 2.2: single facility (F-MAIN), no
# facility differential, and plan tier does not affect the rate. Unlike Hospital 1's
# contract (clause 1.3), Hospital 4's contract does not state a closed set of valid
# plan-tier values -- it only says plan tier is irrelevant to pricing -- so plan tier is
# used as a pricing input to ignore, not as an audit check.

from decimal import Decimal
import re
import pandas as pd

CONTRACT_NUMBER = "INS-H4-2024-2049"
CONTRACT_START = pd.Timestamp("2024-01-01")
CONTRACT_END = pd.Timestamp("2025-12-31")
FACILITY_CODE = "F-MAIN"

contract_path = REPO_ROOT / "contracts" / "hospital_4" / "conditional_reimbursement_agreement.md"
contract_lines = contract_path.read_text(encoding="utf-8").splitlines()

# ---- Section 3: Base Rates ----
rate_rows = []
section = None
for line_number, line in enumerate(contract_lines, start=1):
    if line.startswith("## 3. Base Rates"):
        section = 3
        continue
    if line.startswith("## 4."):
        section = None
    if not line.startswith("|") or section != 3:
        continue
    values = [v.strip() for v in line.strip("|").split("|")]
    if values[0] in {"Service", "---"}:
        continue
    if len(values) != 3 or not values[2].startswith("GBP"):
        continue
    base_rate_cents = int(Decimal(values[2].replace("GBP", "").replace(",", "").strip()) * 100)
    rate_rows.append({
        "service": values[0], "contract_unit": values[1],
        "base_rate_cents": base_rate_cents, "contract_section": "3", "source_line": line_number,
    })

rate_schedule = pd.DataFrame(rate_rows)
assert not rate_schedule.empty
assert rate_schedule["service"].is_unique
assert rate_schedule["base_rate_cents"].gt(0).all()


## Sections 5-10 -- Premiums, quantity limits, bundles, discounts, exclusions, uplifts
#
# Hospital 4's clause numbering differs from Hospital 1's, but the substance of each
# section maps directly onto Hospital 1's Sections 4-10:
#
# | Hospital 4 | Purpose | Hospital 1 equivalent |
# |---|---|---|
# | Sec. 5 Threshold Premiums | aggregate per-Service-Day quantity trigger | Sec. 5 |
# | Sec. 6 Daily Quantity Limits | per-patient per-day cap, 18 services | Sec. 8 |
# | Sec. 7 Bundled Delivery | same-day same-patient rate substitution | Sec. 9 |
# | Sec. 8 Discounts | cumulative hospital-wide utilisation, tiered | Sec. 7 |
# | Sec. 9 Exclusion Windows | non-billable if paired service nearby | Sec. 10 |
# | Sec. 10 Non-Business-Day Uplifts | -- | Sec. 6 |
#
# Section 10 is explicitly "_None._" -- Hospital 4's agreement defines no weekend/non-
# business-day uplift at all. The weekend-uplift machinery is kept (as an empty table) so
# the pricing engine has the same shape as Hospital 1's, but it never fires for this
# hospital.

contract_lines = contract_path.read_text(encoding="utf-8").splitlines()

# ---- Section 5: Threshold Premiums ----
threshold_rows = []
section = None
for line_number, line in enumerate(contract_lines, start=1):
    if line.startswith("## 5. Threshold Premiums"):
        section = 5; continue
    if line.startswith("## 6."):
        section = None
    if not line.startswith("|") or section != 5:
        continue
    values = [v.strip() for v in line.strip("|").split("|")]
    if values[0] in {"Service", "---"} or len(values) != 3:
        continue
    t, u = re.search(r"\d+", values[1]), re.search(r"\d+", values[2])
    if t and u:
        threshold_rows.append({"service": values[0], "threshold_units": int(t.group()),
                                "premium_percent": int(u.group()), "contract_section": "5", "source_line": line_number})
threshold_premiums = pd.DataFrame(threshold_rows)
assert len(threshold_premiums) == 18

# ---- Section 6: Daily Quantity Limits ----
cap_rows = []
section = None
for line_number, line in enumerate(contract_lines, start=1):
    if line.startswith("## 6. Daily Quantity Limits"):
        section = 6; continue
    if line.startswith("## 7."):
        section = None
    if not line.startswith("|") or section != 6:
        continue
    values = [v.strip() for v in line.strip("|").split("|")]
    if values[0] in {"Service", "---"} or len(values) != 2:
        continue
    c = re.search(r"\d+", values[1])
    if c:
        cap_rows.append({"service": values[0], "maximum_units_per_patient_day": int(c.group()),
                          "contract_section": "6", "source_line": line_number})
daily_caps = pd.DataFrame(cap_rows)
assert len(daily_caps) == 18

# ---- Section 7: Bundled Delivery ----
bundle_rows = []
section = None
for line_number, line in enumerate(contract_lines, start=1):
    if line.startswith("## 7. Bundled Delivery"):
        section = 7; continue
    if line.startswith("## 8."):
        section = None
    if not line.startswith("|") or section != 7:
        continue
    values = [v.strip() for v in line.strip("|").split("|")]
    if values[0] in {"Service A", "---"} or len(values) != 4:
        continue
    rate_a = int(Decimal(values[1].replace("GBP", "").replace(",", "").strip()) * 100)
    rate_b = int(Decimal(values[3].replace("GBP", "").replace(",", "").strip()) * 100)
    bundle_rows.append({"service_a": values[0], "bundled_rate_a_cents": rate_a,
                         "service_b": values[2], "bundled_rate_b_cents": rate_b,
                         "contract_section": "7", "source_line": line_number})
bundles = pd.DataFrame(bundle_rows)
assert len(bundles) == 7

# ---- Section 8: Discounts (cumulative, hospital-wide utilisation) ----
discount_rows = []
section = None
for line_number, line in enumerate(contract_lines, start=1):
    if line.startswith("## 8. Discounts"):
        section = 8; continue
    if line.startswith("## 9."):
        section = None
    if not line.startswith("|") or section != 8:
        continue
    values = [v.strip() for v in line.strip("|").split("|")]
    if values[0] in {"Service", "---"} or len(values) != 3:
        continue
    t = re.search(r"\((\d+)\)", values[1])
    d = re.search(r"\((\d+)%\)", values[2])
    if t and d:
        discount_rows.append({"service": values[0], "threshold_units": int(t.group(1)),
                               "discount_percent": int(d.group(1)), "contract_section": "8", "source_line": line_number})
volume_discounts = pd.DataFrame(discount_rows)
assert len(volume_discounts) == 4

# ---- Section 9: Exclusion Windows ----
exclusion_rows = []
section = None
for line_number, line in enumerate(contract_lines, start=1):
    if line.startswith("## 9. Exclusion Windows"):
        section = 9; continue
    if line.startswith("## 10."):
        section = None
    if not line.startswith("|") or section != 9:
        continue
    values = [v.strip() for v in line.strip("|").split("|")]
    if values[0] in {"Service", "---"} or len(values) != 3:
        continue
    d = re.search(r"\d+", values[1])
    if d:
        exclusion_rows.append({"service_a": values[0], "window_days": int(d.group()),
                                "service_b": values[2], "contract_section": "9", "source_line": line_number})
exclusion_windows = pd.DataFrame(exclusion_rows)
assert len(exclusion_windows) == 15

# ---- Section 10: Non-Business-Day Uplifts -- the contract states "_None._" ----
weekend_uplifts = pd.DataFrame(columns=["service", "weekend_uplift_percent", "contract_section", "source_line"])
assert len(weekend_uplifts) == 0
