# Hospital 3 pipeline, part 7/7 — depends on parts 1-6
# (uses line_items, invoices, LINE_CHECK_COLS).

### Aggregate line totals to invoice totals, and final submission output
#
# Aggregation is at invoice-occurrence level first (so a reused invoice ID's two
# transactions are priced independently), then collapsed to one row per invoice ID by
# selecting the later occurrence -- identical to Hospitals 1, 2, 4 and 5. Confidence uses the
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
    "wrong_rate_period",
]
occ_flags = (
    line_items.groupby("invoice_occurrence_key")[LINE_CHECK_COLS + LINE_DIAGNOSTIC_COLS]
    .any().reset_index()
)

occ_invoice = invoices[
    ["invoice_id", "occurrence_rank", "invoice_date", "patient_id", "contract_number",
     "invoice_total_cents", "contract_number_mismatch", "duplicate_invoice_id",
     "unknown_facility_code"]
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
    "wrong_unit_basis", "daily_cap_exceeded", "cross_invoice_duplicate", "exclusion_violation",
    "line_total_arithmetic", "service_not_yet_contracted",
    "bundle_not_applied", "unit_price_mismatch", "wrong_rate_period", "premium_omitted",
    "premium_incorrectly_applied", "weekend_uplift_omitted", "weekend_uplift_incorrectly_applied",
    "volume_discount_omitted", "volume_discount_incorrectly_applied",
    "invoice_total_mismatch", "contract_number_mismatch", "duplicate_invoice_id",
    "unknown_facility_code",
]

CORRECTIVE_RATE_CATS = {
    "unit_price_mismatch", "premium_incorrectly_applied",
    "volume_discount_incorrectly_applied", "weekend_uplift_incorrectly_applied",
    "wrong_rate_period",
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

submission_hospital_3 = invoice_summary[
    ["invoice_id", "flagged", "error_category", "expected_total_cents", "billed_total_cents", "confidence"]
].copy()

required_columns = [
    "invoice_id", "flagged", "error_category",
    "expected_total_cents", "billed_total_cents", "confidence"
]
assert submission_hospital_3.columns.tolist() == required_columns
assert submission_hospital_3["invoice_id"].is_unique
assert submission_hospital_3["flagged"].isin([0, 1]).all()
assert submission_hospital_3["confidence"].between(0, 1).all()
assert len(submission_hospital_3) == invoices["invoice_id"].nunique()

output_path = Path(globals().get("__file__", ".")).resolve().parent / "submission.csv"
submission_hospital_3.to_csv(output_path, index=False)
print(f"Wrote {len(submission_hospital_3)} rows to {output_path}")


## Hospital 3 decision log
#
# Three documents, read together with a stated precedence. Base Agreement clause 1.3
# requires the Base Agreement, Appendix B and any amendment to be read together, and fixes
# the order in a conflict: amendment over Appendix B, Appendix B over the Base Agreement.
# That tells you who wins a conflict but not whether one exists, so the three are
# cross-checked against each other in 02_contract_extraction.py rather than trusted
# individually. Both checks pass on the supplied documents: the amendment's "Rate to
# 31 December 2024" column restates Appendix B exactly for all seven substituted Services
# (so the pre-2025 rate is not in dispute), and the Base Agreement's section 7 caps agree
# exactly with Appendix B's own daily-cap column. Had either disagreed, clause 1.3 would
# have decided it -- but the disagreement itself would have been the finding to report.
#
# Rates are time-dependent, by Service Date. Amendment clause A1.1.1 takes effect on
# 1 January 2025 and A1.1.2 applies it "by Service Date", stating expressly that "The date
# on which an invoice is issued is irrelevant for this purpose". Appendix B B.1 says the
# same from the other side: "the rate in this Appendix continues to apply to Service Dates
# before the amendment's effective date". Roughly half the line items in the data fall
# either side of that date, so this is not a corner case -- pricing everything from one
# rate table would misprice about half the invoices. Only the starting rate is
# date-dependent: A1.4.1 confirms the premiums, caps, bundles, exclusion windows and
# calculation conventions are unchanged and apply to the substituted rates exactly as they
# applied to the rates they replace.
#
# Two Services were not contracted for the whole term. A1.3 adds two Services which
# "become billable in respect of Service Dates on or after 1 January 2025. They were not
# contracted before that date and are not billable in respect of earlier Service Dates."
# A line billing one of them against an earlier Service Date is billing something the
# Provider had no contractual right to bill at all, which is a different finding from a
# wrong rate: it is reported as `service_not_yet_contracted`, and the line is priced
# provisionally at its billed amount rather than at a rate that did not exist on that date.
#
# Billing the rate from the wrong side of the effective date is reported as such. Where a
# substituted-rate Service is billed at the rate that applied on the other side of
# 1 January 2025 -- a superseded rate billed late, or the new rate applied early -- that is
# reported as `wrong_rate_period` rather than as a generic price mismatch, and the generic
# `unit_price_mismatch` is suppressed for that line. This is the error class the amendment
# creates and no other hospital in this exercise can produce.
#
# Conventions carried over unchanged from the other hospitals. Both multipliers are the
# identity (clause 1.5: single facility, no facility differential, all plan tiers
# reimbursed identically). Reused invoice IDs are mapped to transaction groups by the
# line-ID prefix and the later occurrence is reported; daily caps reduce billable quantity
# in ascending line-ID order before multiplication; threshold premiums apply to the whole
# Service Day's aggregate once it exceeds the threshold (clause 4.1); cumulative discounts
# count prior-to-line in Service Date then line-ID order with the deeper tier winning
# (clause 6.1); exclusion windows are measured in either direction and the contract-named
# Service is the non-billable side (section 9); the later duplicate of the same Patient +
# Service + Service Date is not separately billable (clause 10.3); and unmatched or
# unpriceable lines carry the billed amount through provisionally at low confidence rather
# than being dropped or guessed.
#
# No labelled evaluation for Hospital 3. Only Hospital 1 has ground-truth labels, so
# Hospital 3's predictions cannot be scored and are not recalibrated to any
# Hospital-3-specific ground truth. The method and its confidence policy are carried over
# from the Hospital 1 development pass, and the known matcher limitation recorded in
# Hospital 1's decision log carries over here unchanged.
