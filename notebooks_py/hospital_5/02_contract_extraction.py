# Hospital 5 pipeline, part 2/7 — depends on 01_setup.py having run first
# (uses REPO_ROOT).

## Contract structure
#
# Hospital 5's agreement numbers its clauses differently again from Hospitals 1 and 4,
# and it is the first one whose rates genuinely vary by facility and plan tier:
#
# | Hospital 5                        | Purpose                                      | H1 equivalent | H4 equivalent |
# |-----------------------------------|----------------------------------------------|---------------|---------------|
# | 1.2 Facilities                    | F-MAIN / F-NORTH / F-COAST (closed set)      | 1.2 (single)  | 2.2 (single)  |
# | 1.3 Plan tiers                    | BRONZE / SILVER / GOLD (closed set)          | 1.3           | -- (open)     |
# | 3. Effective unit rate            | bundle -> facility -> plan -> premium -> disc | Sec. 3.2      | clause 4.1    |
# | 4. Table 1 Base Rates             | service, unit basis, base rate, daily cap    | Sec. 4        | Sec. 3        |
# | Table 2 Facility Multipliers      | per service x facility                       | -- (all 1x)   | -- (all 1x)   |
# | Table 3 Plan-Tier Multipliers     | per service x tier                           | -- (all 1x)   | -- (all 1x)   |
# | 5. Threshold Premiums             | aggregate per-Patient per-Service-Day        | Sec. 5        | Sec. 5        |
# | 6. Non-Business-Day Uplifts       | weekend uplift                               | Sec. 6        | Sec. 10 (none)|
# | 7. Bundled Services               | same-day same-patient substitution           | Sec. 9        | Sec. 7        |
# | 8. Cumulative Volume Discounts    | hospital-wide cumulative, tiered             | Sec. 7        | Sec. 8        |
# | 9. Exclusion Windows              | non-billable if paired service nearby        | Sec. 10       | Sec. 9        |
# | 10. Invoicing                     | contract no., dates, no double billing       | Sec. 11       | Sec. 11       |
#
# Unlike Hospital 1's Section 8, the daily quantity caps are a column of Table 1 rather
# than a section of their own. Each extracted table's row count is asserted against a
# manual read of the contract before anything downstream trusts it.

CONTRACT_NUMBER = "INS-H5-2024-0731"
CONTRACT_START = pd.Timestamp("2024-01-01")
CONTRACT_END = pd.Timestamp("2025-12-31")
FACILITY_CODES = ["F-MAIN", "F-NORTH", "F-COAST"]   # clause 1.2, Table 2 columns
PLAN_TIERS = ["BRONZE", "SILVER", "GOLD"]           # clause 1.3, Table 3 columns

contract_path = REPO_ROOT / "contracts" / "hospital_5" / "network_reimbursement_agreement.md"
contract_lines = contract_path.read_text(encoding="utf-8").splitlines()


def table_rows(start_prefix, stop_prefix):
    """Markdown table rows between two headings, as stripped cell lists (+ source line)."""
    rows, inside = [], False
    for line_number, line in enumerate(contract_lines, start=1):
        if line.startswith(start_prefix):
            inside = True
            continue
        if inside and line.startswith(stop_prefix):
            break
        if not inside or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] in ("Service", "Service A", "Facility code", "---"):
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        rows.append((line_number, cells))
    return rows


def gbp_to_cents(text):
    return int(Decimal(text.replace("GBP", "").replace(",", "").strip()) * 100)


def first_int(text):
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


# ---- Section 4, Table 1: base rates, unit basis, daily caps ----
rate_rows = []
for line_number, cells in table_rows("## 4. Table 1", "### Table 2"):
    service, unit_basis, rate_text, cap_text = cells
    rate_rows.append({
        "service": service,
        "contract_unit": unit_basis,
        "base_rate_cents": gbp_to_cents(rate_text),
        "daily_cap": first_int(cap_text) if first_int(cap_text) is not None else pd.NA,
        "contract_section": "4/Table 1",
        "source_line": line_number,
    })
rate_schedule = pd.DataFrame(rate_rows)
assert len(rate_schedule) == 84
assert rate_schedule["service"].is_unique
assert rate_schedule["base_rate_cents"].gt(0).all()
assert rate_schedule["daily_cap"].notna().sum() == 9

# ---- Table 2: facility multipliers (per service x facility) ----
facility_rows = []
for line_number, cells in table_rows("### Table 2", "### Table 3"):
    service, *values = cells
    for code, value in zip(FACILITY_CODES, values):
        facility_rows.append({
            "service": service, "facility_code": code, "multiplier": Decimal(value),
            "contract_section": "4/Table 2", "source_line": line_number,
        })
facility_multipliers = pd.DataFrame(facility_rows)
assert len(facility_multipliers) == 84 * 3
assert facility_multipliers["multiplier"].gt(0).all()

# ---- Table 3: plan-tier multipliers (per service x tier) ----
tier_rows = []
for line_number, cells in table_rows("### Table 3", "## 5."):
    service, *values = cells
    for tier, value in zip(PLAN_TIERS, values):
        tier_rows.append({
            "service": service, "plan_tier": tier, "multiplier": Decimal(value),
            "contract_section": "4/Table 3", "source_line": line_number,
        })
tier_multipliers = pd.DataFrame(tier_rows)
assert len(tier_multipliers) == 84 * 3
assert tier_multipliers["multiplier"].gt(0).all()

# Every service priced in Table 1 must have a multiplier row for every facility and tier,
# otherwise a line would silently price without one of the contract's mandatory stages.
assert set(facility_multipliers["service"]) == set(rate_schedule["service"])
assert set(tier_multipliers["service"]) == set(rate_schedule["service"])

# ---- Section 5: threshold premiums (aggregate quantity per Patient per Service Day) ----
threshold_rows = []
for line_number, cells in table_rows("## 5. Threshold", "## 6."):
    service, threshold_text, uplift_text = cells
    threshold_rows.append({
        "service": service,
        "threshold_units": first_int(threshold_text),
        "premium_percent": first_int(uplift_text),
        "contract_section": "5", "source_line": line_number,
    })
threshold_premiums = pd.DataFrame(threshold_rows)
assert len(threshold_premiums) == 10

# ---- Section 6: non-business-day (weekend) uplifts ----
weekend_rows = []
for line_number, cells in table_rows("## 6. Non-Business", "## 7."):
    service, uplift_text = cells
    weekend_rows.append({
        "service": service,
        "weekend_uplift_percent": first_int(uplift_text),
        "contract_section": "6", "source_line": line_number,
    })
weekend_uplifts = pd.DataFrame(weekend_rows)
assert len(weekend_uplifts) == 9

# ---- Section 7: bundled services (columns are A, rate A, B, rate B) ----
bundle_rows = []
for line_number, cells in table_rows("## 7. Bundled", "## 8."):
    service_a, rate_a_text, service_b, rate_b_text = cells
    bundle_rows.append({
        "service_a": service_a, "bundled_rate_a_cents": gbp_to_cents(rate_a_text),
        "service_b": service_b, "bundled_rate_b_cents": gbp_to_cents(rate_b_text),
        "contract_section": "7", "source_line": line_number,
    })
bundles = pd.DataFrame(bundle_rows)
assert len(bundles) == 3

# ---- Section 8: cumulative volume discounts (tiered, hospital-wide) ----
discount_rows = []
for line_number, cells in table_rows("## 8. Cumulative", "## 9."):
    service, threshold_text, discount_text = cells
    discount_rows.append({
        "service": service,
        "threshold_units": first_int(threshold_text),
        "discount_percent": first_int(discount_text),
        "contract_section": "8", "source_line": line_number,
    })
volume_discounts = pd.DataFrame(discount_rows)
assert len(volume_discounts) == 15

# ---- Section 9: exclusion windows (service_a not billable within N days of service_b) ----
exclusion_rows = []
for line_number, cells in table_rows("## 9. Exclusion", "## 10."):
    service_a, window_text, service_b = cells
    exclusion_rows.append({
        "service_a": service_a, "window_days": first_int(window_text), "service_b": service_b,
        "contract_section": "9", "source_line": line_number,
    })
exclusion_windows = pd.DataFrame(exclusion_rows)
assert len(exclusion_windows) == 7

# Fast lookups used by the pricing engine.
FACILITY_MULTIPLIER = {
    (row.service, row.facility_code): row.multiplier
    for row in facility_multipliers.itertuples()
}
TIER_MULTIPLIER = {
    (row.service, row.plan_tier): row.multiplier
    for row in tier_multipliers.itertuples()
}
