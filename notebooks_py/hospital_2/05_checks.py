# Hospital 2 pipeline, part 5/7 — depends on parts 1-4
# (uses invoices, line_items, rate_schedule and the contract constants).

### Article XIII invoicing checks + unit basis, daily cap and arithmetic checks
#
# * 13.1 each invoice is submitted no later than sixty (60) days after the discharge date
#   of the Episode of Care to which it relates;
# * 13.6 each invoice is identified by an invoice number unique across the whole term;
# * 13.11 each invoice quotes the contract number recorded on the face of the Agreement;
# * clause 1.3 the Services are delivered from Main Campus (F-MAIN).
#
# Clauses 13.2-13.5, 13.7-13.10 and 13.12-13.15 restate each of those three requirements
# as an effectiveness condition, a good-faith obligation, a waiver-by-agreement carve-out
# and an "avoidance of doubt" carve-out. They add no further testable condition, so the
# three substantive rules are checked once each rather than fifteen times.
#
# Two further contract constraints are checked before pricing: the per-clause daily caps
# (8 of the 76 services carry one) and the per-clause unit basis against the basis
# actually billed -- the latter is stated in the service clauses themselves ("Where an
# invoice presents this Service on a unit basis other than the one stated in this clause,
# the line item shall be treated as incorrectly presented").
#
# What is deliberately NOT checked here, because Hospital 2's agreement does not contain
# the rule (verified by searching the full text for every wording the other agreements
# use, and asserted in 02_contract_extraction.py):
#   - exclusion windows: Hospital 2 defines none;
#   - duplicate billing of the same Service for the same Patient and Service Date:
#     Hospital 2 contains no such prohibition, so a repeat is not by itself a breach.
# Flagging either would invent a contractual term the Provider never agreed to.
#
# Service dates are checked against the term (clause 1.2) even though Article XIII does
# not restate a service-date rule: a Service Date outside the term is a Service delivered
# outside the period the Agreement covers, and a malformed date cannot be priced at all.

# --- 13.11 / 13.6 / 1.3 invoice-level checks ---
invoices["contract_number_mismatch"] = invoices["contract_number"] != CONTRACT_NUMBER
invoices["duplicate_invoice_id"] = invoices["invoice_id"].duplicated(keep=False)
invoices["unknown_facility_code"] = invoices["facility_code"] != FACILITY_CODE

# --- 13.1 submission window: invoice_date <= discharge_date + 60 days ---
_discharge = pd.to_datetime(invoices["discharge_date"], errors="coerce")
_days_to_invoice = (invoices["invoice_date"] - _discharge).dt.days
invoices["late_submission"] = _days_to_invoice > SUBMISSION_WINDOW_DAYS

# --- service dates (clause 1.2 term) ---
line_items["malformed_service_date"] = line_items["service_date"].isna()
line_items["service_date_out_of_window"] = (
    (~line_items["malformed_service_date"])
    & ((line_items["service_date"] < CONTRACT_START) | (line_items["service_date"] > CONTRACT_END))
)
line_items["service_date_after_invoice_date"] = (
    (~line_items["malformed_service_date"])
    & (line_items["service_date"] > line_items["invoice_date"])
)

# --- billed unit basis vs the unit basis stated in the service's own clause ---
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

# --- daily caps: assessed per Patient per Service Day across all line items (3.4) ---
_cap_map = (
    rate_schedule.loc[rate_schedule["daily_cap"].notna()]
    .set_index("service")["daily_cap"].astype(int).to_dict()
)
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

# --- 3.3 billed line arithmetic, independent of contract pricing ---
line_items["line_total_arithmetic"] = (
    line_items["line_total_cents"] != line_items["unit_price_cents"] * line_items["quantity"]
)

LINE_CHECK_COLS = [
    "malformed_service_date", "service_date_out_of_window", "service_date_after_invoice_date",
    "wrong_unit_basis", "daily_cap_exceeded", "line_total_arithmetic",
]
