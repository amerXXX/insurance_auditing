# Hospital 2 pipeline, part 7/7 — depends on parts 1-6
# (uses line_items, invoices, LINE_CHECK_COLS).

### Aggregate line totals to invoice totals, and final submission output
#
# Aggregation is at invoice-occurrence level first (so a reused invoice ID's two
# transactions are priced independently), then collapsed to one row per invoice ID by
# selecting the later occurrence -- identical to Hospitals 1, 4 and 5. Confidence uses the
# same deterministic rule set: an unknown service caps confidence at 0.35, a provisional
# expected total or a duplicate invoice ID caps it at 0.55, a corrective-rate category
# caps it at 0.80, and two or more simultaneous categories cap it at 0.75.

occ_line = (
    line_items.groupby("invoice_occurrence_key").agg(
        expected_total_cents=("expected_line_total_cents", "sum"),
        any_provisional_expected=("expected_line_total_provisional", "any"),
        any_unmatched=("matched_service", lambda s: s.isna().any()),
        billed_line_total_sum_cents=("line_total_cents", "sum"),
    ).reset_index()
)
occ_line[["invoice_id", "occurrence_rank"]] = occ_line["invoice_occurrence_key"].str.split("::", expand=True)
occ_line["occurrence_rank"] = occ_line["occurrence_rank"].astype(int)

LINE_DIAGNOSTIC_COLS = [
    "bundle_not_applied", "premium_omitted", "premium_incorrectly_applied",
    "volume_discount_omitted", "volume_discount_incorrectly_applied",
    "unit_price_mismatch", "weekend_uplift_omitted", "weekend_uplift_incorrectly_applied",
]
occ_flags = (
    line_items.groupby("invoice_occurrence_key")[LINE_CHECK_COLS + LINE_DIAGNOSTIC_COLS]
    .any().reset_index()
)

occ_invoice = invoices[
    ["invoice_id", "occurrence_rank", "invoice_date", "patient_id", "contract_number",
     "invoice_total_cents", "contract_number_mismatch", "duplicate_invoice_id",
     "unknown_facility_code", "late_submission"]
].copy()
occ_invoice["invoice_occurrence_key"] = (
    occ_invoice["invoice_id"].astype(str) + "::" + occ_invoice["occurrence_rank"].astype(str)
)

occ_summary = (
    occ_invoice.merge(occ_line, on=["invoice_occurrence_key", "invoice_id", "occurrence_rank"], how="left")
    .merge(occ_flags, on="invoice_occurrence_key", how="left")
)

# Clause 3.3: the invoice total is the arithmetic sum of its line totals and nothing else.
occ_summary["invoice_total_mismatch"] = (
    occ_summary["billed_line_total_sum_cents"] != occ_summary["invoice_total_cents"]
)

latest_rank = occ_summary.groupby("invoice_id")["occurrence_rank"].transform("max")
occ_summary["selected_occurrence"] = occ_summary["occurrence_rank"] == latest_rank

PRED_CAT_COLS = [
    "malformed_service_date", "service_date_out_of_window", "service_date_after_invoice_date",
    "wrong_unit_basis", "daily_cap_exceeded", "line_total_arithmetic",
    "bundle_not_applied", "unit_price_mismatch", "premium_omitted",
    "premium_incorrectly_applied", "weekend_uplift_omitted", "weekend_uplift_incorrectly_applied",
    "volume_discount_omitted", "volume_discount_incorrectly_applied",
    "invoice_total_mismatch", "contract_number_mismatch", "duplicate_invoice_id",
    "unknown_facility_code", "late_submission",
]

CORRECTIVE_RATE_CATS = {
    "unit_price_mismatch", "premium_incorrectly_applied",
    "volume_discount_incorrectly_applied", "weekend_uplift_incorrectly_applied",
}


def occurrence_error_category(row):
    cats = [c for c in PRED_CAT_COLS if bool(row.get(c, False))]
    if bool(row.get("any_unmatched", False)):
        cats.append("unknown_service")
    return "|".join(dict.fromkeys(cats))


def occurrence_confidence(row):
    cats = [c for c in PRED_CAT_COLS if bool(row.get(c, False))]
    has_unknown = bool(row.get("any_unmatched", False))
    confidence = 0.95 if not cats and not has_unknown else 0.90
    if has_unknown:
        confidence = min(confidence, 0.35)
    if bool(row.get("duplicate_invoice_id", False)):
        confidence = min(confidence, 0.55)
    if bool(row.get("any_provisional_expected", False)):
        confidence = min(confidence, 0.55)
    if any(c in CORRECTIVE_RATE_CATS for c in cats):
        confidence = min(confidence, 0.80)
    if len(cats) >= 2:
        confidence = min(confidence, 0.75)
    return round(confidence, 2)


occ_summary["error_category"] = occ_summary.apply(occurrence_error_category, axis=1)
occ_summary["confidence"] = occ_summary.apply(occurrence_confidence, axis=1)
occ_summary["flagged"] = (occ_summary["error_category"] != "").astype(int)

invoice_summary = occ_summary[occ_summary["selected_occurrence"]].copy()
invoice_summary = invoice_summary.sort_values(["invoice_id"]).reset_index(drop=True)

invoice_summary["billed_total_cents"] = invoice_summary["invoice_total_cents"]
invoice_summary["expected_total_cents"] = invoice_summary["expected_total_cents"].round().astype("Int64")

print("Flagged counts:", invoice_summary["flagged"].value_counts().to_dict())
print("Confidence distribution:", invoice_summary["confidence"].value_counts().sort_index().to_dict())
print("Invoices with provisional expected totals:", int(invoice_summary["any_provisional_expected"].sum()))
print("Match status (distinct descriptions):", description_matches["match_status"].value_counts().to_dict())

submission_hospital_2 = invoice_summary[
    ["invoice_id", "flagged", "error_category", "expected_total_cents", "billed_total_cents", "confidence"]
].copy()

required_columns = [
    "invoice_id", "flagged", "error_category",
    "expected_total_cents", "billed_total_cents", "confidence"
]
assert submission_hospital_2.columns.tolist() == required_columns
assert submission_hospital_2["invoice_id"].is_unique
assert submission_hospital_2["flagged"].isin([0, 1]).all()
assert submission_hospital_2["confidence"].between(0, 1).all()
assert len(submission_hospital_2) == invoices["invoice_id"].nunique()

output_path = Path(globals().get("__file__", ".")).resolve().parent / "predictions.csv"
submission_hospital_2.to_csv(output_path, index=False)
print(f"Wrote {len(submission_hospital_2)} rows to {output_path}")


## Hospital 2 decision log
#
# Prose contract, no tables. Clause 1.4 states the rates "are not gathered into a single
# schedule"; each appears in the Article describing its Service, and the Articles "are not
# ordered by clinical speciality". Thirteen "Contracted Services (N Group)" Articles are
# interleaved with unrelated boilerplate Articles. Every rate, unit basis, daily cap,
# threshold premium, non-business-day uplift, volume discount and bundle is therefore
# parsed out of prose sentences, with the figure in brackets after the words
# ("twenty-four (24)", "thirty percent (30%)").
#
# Extraction completeness is asserted, not assumed. Each provision count parsed is checked
# against the number of times the corresponding phrase occurs in the raw text: 76 services
# (76 "at the rate of GBP"), 8 daily caps, 9 threshold premiums, 8 non-business-day
# uplifts, 12 discount tiers and 6 bundle sentences (3 unordered pairs). A clause the
# parser fails to recognise fails the run rather than silently dropping a contract rule --
# the failure mode that matters most here, since a missed rule prices invoices as if the
# Provider had never agreed to it.
#
# Two provisions are genuinely absent, and the absence is load-bearing. Hospital 2 defines
# no exclusion windows, and it contains no prohibition on billing the same Service twice
# for the same Patient and Service Date -- both verified by searching the full text for
# every wording the other three agreements use, and asserted in 02_contract_extraction.py
# so a future contract revision cannot reintroduce them silently. Hospitals 1, 4 and 5 all
# zero out a later duplicate line; doing the same here would invent a term this Provider
# never agreed to, so repeats are priced normally and are not flagged.
#
# Both multipliers are the identity. Clause 1.3 gives a single facility (F-MAIN), states
# "No facility differential applies", and applies the rates "irrespective of the Patient's
# plan tier". Stages (b) and (c) of clause 3.2's order are therefore skipped rather than
# applied as 1x multiplications, which could only introduce rounding noise. Plan tier is
# not an audit check here: the Agreement never enumerates a closed set of valid tiers, so
# an unusual tier value is not a contractual breach (the same reading taken for Hospital 4,
# and the opposite of Hospitals 1 and 5 which do enumerate one).
#
# Article XIII is fifteen clauses restating three rules. 13.1 (submission within sixty days
# of the discharge date), 13.6 (invoice number unique across the term) and 13.11 (quoting
# the contract number) are the substantive requirements; 13.2-13.5, 13.7-13.10 and
# 13.12-13.15 restate each as an effectiveness condition, a good-faith obligation, a
# waiver-by-agreement carve-out and an avoidance-of-doubt carve-out. They add no further
# testable condition, so each rule is checked once. The submission-window rule is new to
# this hospital and is checked against the invoice's own discharge date; on the supplied
# data no invoice breaches it (the latest is ten days after discharge), so the check is
# clean rather than inert -- it is wired into the prediction and would fire if breached.
#
# Service dates are checked against the term even though Article XIII does not restate a
# service-date rule. Clause 1.2 fixes the term, and a Service Date outside it is a Service
# delivered outside the period the Agreement covers; a malformed date cannot be priced at
# all. This is an inference from the term clause rather than an express invoicing rule, and
# is recorded here as such. It is also supported by the Hospital 1 labels, where every
# invoice carrying an out-of-term or after-invoice-date Service Date is labelled erroneous.
#
# Conventions carried over unchanged from Hospitals 1, 4 and 5. Reused invoice IDs are
# mapped to transaction groups by the line-ID prefix and the later occurrence is reported;
# daily caps reduce billable quantity in ascending line-ID order before multiplication;
# threshold premiums apply to the whole Service Day's quantity once the aggregate exceeds
# the threshold (clause 3.4 puts this beyond doubt for Hospital 2, where the other
# contracts left it to be inferred); cumulative discounts count prior-to-line in Service
# Date then line-ID order with the deeper tier winning and no compounding (clause 3.5,
# again express here); and unmatched or unpriceable lines carry the billed amount through
# provisionally at low confidence rather than being dropped or guessed.
#
# No labelled evaluation for Hospital 2. Only Hospital 1 has ground-truth labels, so
# Hospital 2's predictions cannot be scored and are not recalibrated to any
# Hospital-2-specific ground truth. The method and its confidence policy are carried over
# from the Hospital 1 development pass. The known matcher limitation recorded in Hospital
# 1's decision log carries over here unchanged.
