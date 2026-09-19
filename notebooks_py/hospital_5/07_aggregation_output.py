# Hospital 5 pipeline, part 7/7 — depends on parts 1-6
# (uses line_items, invoices, LINE_CHECK_COLS).

### Aggregate line totals to invoice totals, and final submission output
#
# Aggregation is at invoice-occurrence level first (so a reused invoice ID's two
# transactions are priced independently), then collapsed to one row per invoice ID by
# selecting the later occurrence -- identical to Hospitals 1 and 4. Confidence is a
# deterministic audit-policy score, not a probability, using the same rule set: an
# unknown service caps confidence at 0.35, a provisional expected total or a duplicate
# invoice ID caps it at 0.55, a "corrective-rate" category (unit price / premium /
# uplift / discount / multiplier mismatch) caps it at 0.80, and two or more simultaneous
# error categories cap it at 0.75.

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
    "facility_multiplier_misapplied", "plan_tier_multiplier_misapplied",
]
occ_flags = (
    line_items.groupby("invoice_occurrence_key")[LINE_CHECK_COLS + LINE_DIAGNOSTIC_COLS]
    .any().reset_index()
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

# The invoice total is the sum of its line totals and nothing else.
occ_summary["invoice_total_mismatch"] = (
    occ_summary["billed_line_total_sum_cents"] != occ_summary["invoice_total_cents"]
)

# Reused invoice IDs: report the later invoice occurrence (same convention as Hospitals 1 and 4).
latest_rank = occ_summary.groupby("invoice_id")["occurrence_rank"].transform("max")
occ_summary["selected_occurrence"] = occ_summary["occurrence_rank"] == latest_rank

PRED_CAT_COLS = [
    "malformed_service_date", "service_date_out_of_window", "service_date_after_invoice_date",
    "wrong_unit_basis", "daily_cap_exceeded", "cross_invoice_duplicate", "exclusion_violation",
    "line_total_arithmetic", "unknown_facility_code", "unknown_plan_tier",
    "bundle_not_applied", "unit_price_mismatch", "premium_omitted",
    "premium_incorrectly_applied", "weekend_uplift_omitted", "weekend_uplift_incorrectly_applied",
    "volume_discount_omitted", "volume_discount_incorrectly_applied",
    "facility_multiplier_misapplied", "plan_tier_multiplier_misapplied",
    "invoice_total_mismatch", "contract_number_mismatch", "duplicate_invoice_id",
]

CORRECTIVE_RATE_CATS = {
    "unit_price_mismatch", "premium_incorrectly_applied",
    "volume_discount_incorrectly_applied", "weekend_uplift_incorrectly_applied",
    "facility_multiplier_misapplied", "plan_tier_multiplier_misapplied",
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

# Hospital 5 output in the exact repository submission schema, written as this
# hospital's own predictions.csv (uniform per-hospital naming, so ../main.py
# can combine every hospital_*/predictions.csv generically). Only the combined
# file that main.py writes at the repo root is named submission.csv -- there is
# exactly one submission file in this repository.
submission_hospital_5 = invoice_summary[
    ["invoice_id", "flagged", "error_category", "expected_total_cents", "billed_total_cents", "confidence"]
].copy()

required_columns = [
    "invoice_id", "flagged", "error_category",
    "expected_total_cents", "billed_total_cents", "confidence"
]
assert submission_hospital_5.columns.tolist() == required_columns
assert submission_hospital_5["invoice_id"].is_unique
assert submission_hospital_5["flagged"].isin([0, 1]).all()
assert submission_hospital_5["confidence"].between(0, 1).all()
assert len(submission_hospital_5) == invoices["invoice_id"].nunique()

output_path = Path(globals().get("__file__", ".")).resolve().parent / "predictions.csv"
submission_hospital_5.to_csv(output_path, index=False)
print(f"Wrote {len(submission_hospital_5)} rows to {output_path}")


## Hospital 5 decision log
#
# Contract-structure mapping. Hospital 5's network_reimbursement_agreement.md numbers its
# clauses differently again from Hospitals 1 and 4 (base rates are Table 1 under Section 4
# rather than Section 4 or Section 3; threshold premiums 5; non-business-day uplifts 6;
# bundled services 7; cumulative volume discounts 8; exclusion windows 9; invoicing rules
# 10). Each section was re-extracted from its actual heading rather than assumed to line up
# positionally with an earlier hospital, and every extracted table's row count is asserted
# against a manual read of the contract (84 base rates, 84x3 facility multipliers, 84x3
# plan-tier multipliers, 10 threshold premiums, 9 weekend uplifts, 3 bundle pairs, 15
# discount tiers across 9 services, 7 exclusion windows). The daily caps are a column of
# Table 1 here, not a section of their own as in Hospital 1.
#
# The rate tables are supplied twice. network_reimbursement_agreement_rate_tables.pdf
# repeats Tables 1-3. Its text was extracted and compared value-by-value against the
# Markdown before this pipeline was written: all 84 services agree exactly on unit basis,
# base rate, daily cap, all three facility multipliers and all three plan-tier multipliers.
# The Markdown is parsed as the single source of truth; the PDF is a redundant rendering,
# not a separate authority. Had the two disagreed, that disagreement -- not a choice
# between them -- would have been the finding to report.
#
# Facility and plan-tier multipliers are real here. This is the first contract in the
# exercise where stages (b) and (c) of the pricing order do actual work: Table 2 varies the
# rate by facility (F-MAIN / F-NORTH / F-COAST) and Table 3 by plan tier (BRONZE / SILVER /
# GOLD), per service. The data exercises all three facilities and all three tiers. Clause
# 3.2's "rounding after each individual step" therefore matters materially, since two
# multiplications now precede any premium or discount; all arithmetic uses Decimal with
# half-up rounding at each stage rather than floating point.
#
# Two error categories added for this contract. Because a wrong facility or plan-tier
# multiplier is a distinct and likely billing error here, `facility_multiplier_misapplied`
# and `plan_tier_multiplier_misapplied` are reported when the billed unit price matches the
# rate the chain would produce under a *different* facility or tier than the invoice
# records, holding the rest of the chain correct. They are treated as corrective-rate
# categories for confidence purposes, and the generic `unit_price_mismatch` is suppressed
# when either fires, so the more specific finding is the one reported.
#
# Unknown facility code or plan tier is a pricing failure, not a cosmetic one. Clause 10.1
# requires the invoice to quote both, and each selects a mandatory multiplier; a line
# carrying a value outside the contract's closed sets cannot be priced from the contract at
# all. Such lines carry the billed amount through provisionally at reduced confidence and
# are flagged, rather than being priced on an assumed multiplier. On the supplied data both
# checks are clean (every invoice quotes one of the three facilities and one of the three
# tiers), so neither category fires -- they are kept because they are genuine contract
# requirements, and they are wired into the prediction rather than left as dead diagnostics.
#
# Premium and uplift ordering. Clause 3.1 groups "any premium or uplift" into a single
# stage (d). Where both a Section 5 threshold premium and a Section 6 non-business-day
# uplift apply to the same line, they are applied in that order within the stage -- the
# convention Hospital 1 used where both existed. The contract does not state an order
# between them; an alternative reading applying them in the reverse order would differ only
# by rounding, and only on lines where both fire.
#
# Secondary price evidence models the multipliers. plausible_unit_prices() is used only to
# break a text tie between structurally-compatible candidates. For Hospitals 1 and 4 it was
# built from base/premium/discount-derived prices; on Hospital 5 a set built that way would
# match nothing, because every billed price carries a facility and a tier multiplier. It is
# therefore built across all facility x tier combinations for the service, and -- unlike
# Hospitals 1 and 4 -- across the service's bundled substituted rate too, closing the gap
# their decision logs recorded as a known limitation. A wider plausible set makes it less
# likely that exactly one candidate qualifies, so the failure direction is more
# needs_review, never a more confident wrong guess.
#
# Conventions carried over unchanged from Hospitals 1 and 4. Reused invoice IDs are mapped
# to transaction groups by the line-ID prefix and the later occurrence is the one reported;
# the exclusion-window service_a is the non-billable side; the later duplicate of the same
# patient + service + Service Day is the non-billable one; daily caps reduce billable
# quantity before multiplication; unmatched or unpriceable lines carry the billed amount
# through provisionally at low confidence rather than being dropped or guessed.
#
# No labelled evaluation for Hospital 5. Only Hospital 1 has ground-truth labels in this
# exercise, so Hospital 5's predictions cannot be scored and are not recalibrated to any
# Hospital-5-specific ground truth. The method and its confidence policy are carried over
# from the Hospital 1 development pass, where they were calibrated. The known limitations
# recorded in Hospital 1's decision log (notably the matcher's treatment of descriptions
# that state no clinical specialty) carry over here unchanged.
