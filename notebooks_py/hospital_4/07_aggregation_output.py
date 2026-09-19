# Hospital 4 pipeline, part 7/7 — depends on parts 1-6
# (uses line_items, invoices, LINE_CHECK_COLS, REPO_ROOT).

### Aggregate line totals to invoice totals, and final submission output
#
# Aggregation is at invoice-occurrence level first (so a reused invoice ID's two
# transactions are priced independently), then collapsed to one row per invoice ID by
# selecting the later occurrence -- identical to Hospital 1's convention. Confidence is a
# deterministic audit-policy score, not a probability, using the same rule set as Hospital
# 1: unknown-service caps confidence at 0.35, a provisional expected total or a duplicate
# invoice ID caps it at 0.55, a "corrective-rate" category (unit price / premium / discount
# mismatch) caps it at 0.80, and two or more simultaneous error categories cap it at 0.75.

# Aggregate at invoice-occurrence level first, then collapse reused IDs to one prediction row.
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

occ_flags = (
    line_items.groupby("invoice_occurrence_key")[LINE_CHECK_COLS + [
        "bundle_not_applied", "premium_omitted", "premium_incorrectly_applied",
        "volume_discount_omitted", "volume_discount_incorrectly_applied",
        "unit_price_mismatch", "weekend_uplift_omitted", "weekend_uplift_incorrectly_applied"
    ]].any().reset_index()
)

occ_invoice = invoices[
    ["invoice_id", "occurrence_rank", "invoice_date", "patient_id", "contract_number",
     "invoice_total_cents", "contract_number_mismatch", "duplicate_invoice_id"]
].copy()
occ_invoice["invoice_occurrence_key"] = (
    occ_invoice["invoice_id"].astype(str) + "::" + occ_invoice["occurrence_rank"].astype(str)
)

occ_summary = (
    occ_invoice.merge(occ_line, on=["invoice_occurrence_key", "invoice_id", "occurrence_rank"], how="left")
    .merge(occ_flags, on="invoice_occurrence_key", how="left")
)

# Explicit invoice-total arithmetic mismatch (clause 4.4: invoice total is the sum of line
# totals and nothing else).
occ_summary["invoice_total_mismatch"] = (
    occ_summary["billed_line_total_sum_cents"] != occ_summary["invoice_total_cents"]
)

# Reused invoice IDs: report the later invoice occurrence (same convention as Hospital 1).
latest_rank = occ_summary.groupby("invoice_id")["occurrence_rank"].transform("max")
occ_summary["selected_occurrence"] = occ_summary["occurrence_rank"] == latest_rank

PRED_CAT_COLS = [
    "malformed_service_date", "service_date_out_of_window", "service_date_after_invoice_date",
    "wrong_unit_basis", "daily_cap_exceeded", "cross_invoice_duplicate", "exclusion_violation",
    "line_total_arithmetic", "bundle_not_applied", "unit_price_mismatch", "premium_omitted",
    "premium_incorrectly_applied", "weekend_uplift_omitted", "weekend_uplift_incorrectly_applied",
    "volume_discount_omitted", "volume_discount_incorrectly_applied", "invoice_total_mismatch",
    "contract_number_mismatch",
    "duplicate_invoice_id"
]

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
    if any(c in {"unit_price_mismatch", "premium_incorrectly_applied",
               "volume_discount_incorrectly_applied", "weekend_uplift_incorrectly_applied"}
           for c in cats):
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

# Hospital 4 output in the exact repository submission schema, written as this
# hospital's own predictions.csv (uniform per-hospital naming, so ../main.py
# can combine every hospital_*/predictions.csv generically). Only the combined
# file that main.py writes at the repo root is named submission.csv -- there is
# exactly one submission file in this repository.
submission_hospital_4 = invoice_summary[
    ["invoice_id", "flagged", "error_category", "expected_total_cents", "billed_total_cents", "confidence"]
].copy()

required_columns = [
    "invoice_id", "flagged", "error_category",
    "expected_total_cents", "billed_total_cents", "confidence"
]
assert submission_hospital_4.columns.tolist() == required_columns
assert submission_hospital_4["invoice_id"].is_unique
assert submission_hospital_4["flagged"].isin([0, 1]).all()
assert submission_hospital_4["confidence"].between(0, 1).all()
assert len(submission_hospital_4) == invoices["invoice_id"].nunique()

output_path = Path(globals().get("__file__", ".")).resolve().parent / "predictions.csv"
submission_hospital_4.to_csv(output_path, index=False)
print(f"Wrote {len(submission_hospital_4)} rows to {output_path}")


## Hospital 4 decision log
#
# Contract-structure mapping. Hospital 4's conditional_reimbursement_agreement.md
# numbers its sections differently from Hospital 1's provider_services_agreement.md
# (Base Rates is Section 3 not 4, Threshold Premiums is still 5, Daily Quantity Limits is 6
# not 8, Bundled Delivery is 7 not 9, Discounts is 8 not 7, Exclusion Windows is 9 not 10,
# Non-Business-Day Uplifts is 10 not 6). Each section was re-extracted from the actual
# clause headers rather than assumed to line up positionally with Hospital 1's, and the
# extracted row counts were asserted against a manual read of the contract (98 base rates,
# 18 threshold premiums, 18 daily caps, 7 bundle pairs, 4 discount tiers across 3 services,
# 15 exclusion windows, 0 weekend uplifts).
#
# No weekend/non-business-day uplift. Section 10 of Hospital 4's agreement is the single
# word "_None._". The weekend-uplift columns and pricing step are kept in the code for
# schema parity with Hospital 1's pipeline but structurally never fire, since the uplift
# table is empty.
#
# Plan tier is not an audit check for Hospital 4. Hospital 1's contract named a closed
# set of valid tiers (clause 1.3); Hospital 4's contract (clause 2.2) only says plan tier
# does not affect the rate. Absent a stated closed set, an unusual plan-tier value is not
# treated as a contract violation here -- this is a reading I could not verify further from
# the contract text alone.
#
# Clause 11.3 duplicate-billing interpretation. 11.3 prohibits billing the same Service
# twice for the same Patient + Service Date "whether on one invoice or across several," and
# ties this explicitly to the Section 6.2 aggregation principle. I read this as a general
# no-double-billing rule for *every* service (not only the 18 services with a stated
# Section 6 numeric cap), and applied the same later-occurrence-is-the-duplicate convention
# Hospital 1 used. This is the most consequential ambiguity call in this pass: an
# alternative reading would confine 11.3 to only the capped services, which would leave the
# 5 flagged cross-invoice duplicates on uncapped services unflagged.
#
# Bundle rates as secondary price evidence -- limitation found, then closed.
# plausible_unit_prices() (used to break text-matching ties) originally considered only
# base/premium/discount-derived prices, not bundle-substituted rates. That left the
# ambiguous description "CARDIAC physio SESS" unresolvable: it ties between "Outpatient
# Cardiac Physiotherapy Session" and "Emergency Cardiac Physiotherapy Session", and its
# billed price (GBP 84.00) is exactly the Section 7 bundled rate for the latter -- a value
# the plausible set did not contain, so no candidate looked consistent.
#
# The cost was larger than it first appeared. An unmatched description also stops the
# bundle being detected at all, which then misprices the partner Service on the same
# invoice. "CARDIAC physio SESS" and "RHEUM rehabilitation PROGRAMME" between them left 48
# invoices either flagged unknown_service or carrying a spurious unit_price_mismatch on
# their partners "Extended Obstetric Case Conference" and "Ambulatory Paediatric Critical
# Care Occupancy" -- which is why Hospital 4 was flagging 12.7% of its invoices while the
# other three hospitals sat near 7%.
#
# Including bundled rates in the plausible set resolves both descriptions by secondary
# price support (each to the bundle partner the billed price implies), and brings the flag
# rate to 7.5%, in line with the others. Clean-invoice reconciliation remains exactly 100%,
# so the change resolved descriptions rather than loosening the pricing check.
#
# Reused invoice IDs and occurrence mapping. Identical convention to Hospital 1: the
# line-ID group prefix recovers the original transaction group, mapped chronologically onto
# invoice-table occurrences, and the later occurrence is the one reported in the
# one-row-per-invoice submission.
#
# No labelled evaluation for Hospital 4. Only Hospital 1 has ground-truth labels in this
# exercise; Hospital 4's predictions could not be scored against labels and are not
# recalibrated to any Hospital-4-specific ground truth. The method and its calibration are
# carried over from the Hospital 1 development pass.
