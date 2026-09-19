# Hospital 3 pipeline, part 5/7 — depends on parts 1-4
# (uses invoices, line_items, rate_schedule, daily_caps, exclusion_windows and the
# contract constants).

### Section 10 invoicing checks + unit basis, daily cap, duplicate and exclusion checks
#
# * 10.1 each invoice quotes the contract number and carries an invoice number unique
#   across the term;
# * 10.2 every Service Date falls within the term and may not fall after the invoice date;
# * 10.3 the same Service may not be billed twice for the same Patient and Service Date,
#   whether on one invoice or across several -- the later occurrence (by invoice date,
#   then line ID) is the non-billable duplicate, the convention used for Hospitals 1, 4
#   and 5 (Hospital 2's agreement contains no such rule, so it is the exception).
# * 1.5 the Services are delivered from Main Campus (F-MAIN).
#
# Section 7 daily caps and the Appendix B unit basis are checked before pricing, and
# section 9 exclusion windows remove the excluded (non-billable) service line from the
# expected reimbursement.
#
# One check here is specific to Hospital 3. Amendment clause A1.3 adds two Services which
# "become billable in respect of Service Dates on or after 1 January 2025. They were not
# contracted before that date and are not billable in respect of earlier Service Dates."
# A line billing one of them against an earlier Service Date is therefore billing a
# Service the Provider had no contractual right to bill at all -- a distinct finding from
# a wrong rate, and one no other hospital in this exercise can produce.

# --- 10.1 / 1.5 invoice-level checks ---
invoices["contract_number_mismatch"] = invoices["contract_number"] != CONTRACT_NUMBER
invoices["duplicate_invoice_id"] = invoices["invoice_id"].duplicated(keep=False)
invoices["unknown_facility_code"] = invoices["facility_code"] != FACILITY_CODE

# --- 10.2 service dates ---
line_items["malformed_service_date"] = line_items["service_date"].isna()
line_items["service_date_out_of_window"] = (
    (~line_items["malformed_service_date"])
    & ((line_items["service_date"] < CONTRACT_START) | (line_items["service_date"] > CONTRACT_END))
)
line_items["service_date_after_invoice_date"] = (
    (~line_items["malformed_service_date"])
    & (line_items["service_date"] > line_items["invoice_date"])
)

# --- A1.3: a Service billed against a Service Date before it was contracted ---
_contracted_from = CONTRACTED_FROM
line_items["service_not_yet_contracted"] = [
    bool(pd.notna(svc) and pd.notna(sd) and sd < _contracted_from.get(svc, CONTRACT_START))
    for svc, sd in zip(line_items["matched_service"], line_items["service_date"])
]

# --- billed unit basis vs the Appendix B unit basis ---
CONTRACT_UNIT_TO_BILLED = {
    "per hour": "per_hour", "per day of service": "per_day", "per visit": "per_visit",
    "per test": "per_test", "per procedure": "per_procedure", "per night of occupancy": "per_night",
    "per item supplied": "per_item", "per unit dispensed": "per_unit_dispensed",
    "per hour, per item": "per_hour_per_item",
}
assert set(rate_schedule["contract_unit"]) <= set(CONTRACT_UNIT_TO_BILLED), (
    "An unmapped unit basis would make wrong_unit_basis silently never fire: "
    f"{set(rate_schedule['contract_unit']) - set(CONTRACT_UNIT_TO_BILLED)}"
)
_unit_map = rate_schedule.set_index("service")["contract_unit"].map(CONTRACT_UNIT_TO_BILLED).to_dict()
line_items["expected_unit_basis"] = line_items["matched_service"].map(_unit_map)
line_items["wrong_unit_basis"] = (
    line_items["expected_unit_basis"].notna()
    & (line_items["expected_unit_basis"] != line_items["unit_basis_as_billed"])
)

# --- section 7 daily caps: per Patient per Service Day, allocated in line-ID order ---
_cap_map = dict(zip(daily_caps["service"], daily_caps["maximum_units_per_patient_day"]))
_valid_priced = line_items.dropna(subset=["matched_service", "service_date", "patient_id"]).copy()
_valid_priced = _valid_priced.sort_values(["patient_id", "matched_service", "service_date", "line_id"])
_valid_priced["_day_qty_prior"] = _valid_priced.groupby(
    ["patient_id", "matched_service", "service_date"]
)["quantity"].cumsum() - _valid_priced["quantity"]
_valid_priced["_cap"] = _valid_priced["matched_service"].map(_cap_map)
_valid_priced["billable_quantity"] = _valid_priced["quantity"]
_mask_capped = _valid_priced["_cap"].notna()
_valid_priced.loc[_mask_capped, "billable_quantity"] = (
    _valid_priced.loc[_mask_capped, "quantity"]
    .where(_valid_priced.loc[_mask_capped, "_day_qty_prior"] < _valid_priced.loc[_mask_capped, "_cap"], 0)
    .clip(upper=_valid_priced.loc[_mask_capped, "_cap"] - _valid_priced.loc[_mask_capped, "_day_qty_prior"])
    .clip(lower=0)
)
line_items["_day_qty_prior"] = pd.NA
line_items["billable_quantity"] = line_items["quantity"]
line_items.loc[_valid_priced.index, "_day_qty_prior"] = _valid_priced["_day_qty_prior"]
line_items.loc[_valid_priced.index, "billable_quantity"] = _valid_priced["billable_quantity"]
line_items["daily_cap_exceeded"] = line_items["billable_quantity"] < line_items["quantity"]

# --- 10.3 duplicate patient/service/date billing (one invoice or across several) ---
line_items["cross_invoice_duplicate"] = False
_dup_valid = _valid_priced[_valid_priced["matched_service"].notna()].copy()
for _, grp in _dup_valid.groupby(["patient_id", "matched_service", "service_date"], dropna=False):
    if len(grp) < 2:
        continue
    ordered = grp.sort_values(["invoice_date", "line_id"])
    line_items.loc[ordered.index[1:], "cross_invoice_duplicate"] = True

# --- section 9 exclusion windows (measured in either direction) ---
line_items["exclusion_violation"] = False
for _, rule in exclusion_windows.iterrows():
    a_rows = _valid_priced[_valid_priced["matched_service"] == rule["service_a"]]
    b_rows = _valid_priced[_valid_priced["matched_service"] == rule["service_b"]]
    if a_rows.empty or b_rows.empty:
        continue
    merged = a_rows[["patient_id", "service_date"]].reset_index().merge(
        b_rows[["patient_id", "service_date"]].reset_index(),
        on="patient_id", suffixes=("_a", "_b"),
    )
    diff_days = (merged["service_date_a"] - merged["service_date_b"]).abs().dt.days
    violations = merged[diff_days <= int(rule["window_days"])].copy()
    if not violations.empty:
        line_items.loc[violations["index_a"], "exclusion_violation"] = True

# --- 3.3 billed line arithmetic, independent of contract pricing ---
line_items["line_total_arithmetic"] = (
    line_items["line_total_cents"] != line_items["unit_price_cents"] * line_items["quantity"]
)

LINE_CHECK_COLS = [
    "malformed_service_date", "service_date_out_of_window", "service_date_after_invoice_date",
    "wrong_unit_basis", "daily_cap_exceeded", "cross_invoice_duplicate", "exclusion_violation",
    "line_total_arithmetic", "service_not_yet_contracted",
]
