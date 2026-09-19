# Hospital 1 pipeline, part 9/9 — depends on parts 1-7
# (uses invoice_summary).
#
# Hospital 1 output in the exact submission-template schema, written as this
# hospital's own submission.csv (uniform per-hospital naming, so ../main.py
# can combine every hospital_*/submission.csv generically). Hospital 1 is a
# calibration artifact only, though -- it is NOT the scored holdout; its
# predictions are checked against labels/hospital_1_labels.csv in 08_evaluation.py.

submission_hospital_1 = invoice_summary[
    ["invoice_id", "flagged", "error_category", "expected_total_cents", "billed_total_cents", "confidence"]
].copy()

# Submission schema sanity checks.
required_columns = [
    "invoice_id", "flagged", "error_category",
    "expected_total_cents", "billed_total_cents", "confidence"
]
assert submission_hospital_1.columns.tolist() == required_columns
assert submission_hospital_1["invoice_id"].is_unique
assert submission_hospital_1["flagged"].isin([0, 1]).all()
assert submission_hospital_1["confidence"].between(0, 1).all()

output_path = Path(globals().get("__file__", ".")).resolve().parent / "submission.csv"
submission_hospital_1.to_csv(output_path, index=False)
print(f"Wrote {len(submission_hospital_1)} rows to {output_path}")


## Hospital 1 decision log
#
# Uncertainty handling. Unmatched/ambiguous service descriptions are flagged for
# review with low confidence rather than silently treated as valid. Billed price is
# used only as secondary evidence when text and structural constraints leave a
# genuinely narrow candidate set (never the primary basis for identifying a service).
#
# Corrected totals. Exclusion-window and later cross-invoice-duplicate lines are
# treated as non-billable (expected total 0) in the corrected total. Daily quantity
# caps reduce billable quantity before multiplication. Unknown services or malformed
# dates retain their billed line amount provisionally and are marked low-confidence,
# because a defensible contract rate cannot be established automatically.
#
# Development calibration. The H1 development labels were used to test threshold and
# ambiguity choices while building the method; the runtime detector never reads the
# label file. The reused-invoice-ID occurrence convention (report the later occurrence)
# was validated against H1 and then encoded as a deterministic rule -- this calibration
# is disclosed rather than presented as an unbiased test result.
#
# Development-set discrepancy (daily caps). Four H1 labelled daily-cap cases do not
# reproduce the labelled corrected total under a literal cap-clip reading. Investigated
# at length (see Prompts/hospital1-label-residual-review.v1.md): ruled out cross-invoice
# cumulative counts (each is the only line for that patient+service+date in the whole
# dataset) and a unit-basis mismatch (billed and contract units agree); Section 8 of the
# contract carries no interpretive clause, just a bare table. The implied "label-correct"
# billable quantity is exactly 3 units across three of the four cases, independent of the
# service's own stated cap (4, 12, 8) or billed quantity (9, 14, 11) -- no formula or
# contract clause reproduces that. This looks like an artifact of how the synthetic test
# data was generated (a fixed true quantity, inflated to trigger the cap check), not a
# rule a real auditor could recover from the visible evidence. The contract-faithful cap
# interpretation is kept rather than reverse-fitted to the labels, and the residual is
# reported explicitly (see 08_evaluation.py's "Expected-total residuals by failure type").
#
# Matcher limitation (INV-H1-000236). "Fract Outpatient Radiotherapy" is matched
# confidently (score 0.736, gap 0.315 over the runner-up) to "Outpatient Metabolic
# Radiotherapy Fraction" -- but the description states no clinical-specialty word at
# all, so nothing confirms "Metabolic" specifically; the label reads this as
# unknown_service. Two general fixes were tested and rejected: tightening
# MIN_SCORE/GAP_THRESHOLD doesn't even change this match's outcome while it breaks two
# other correct matches; a unit-basis veto in the matcher would also reject 11 other
# lines that are genuinely correct matches billed on the wrong unit (the
# wrong_unit_basis detection category itself). Documented as an accepted limitation
# rather than special-cased.
#
# Category vocabulary. The detector keeps precise internal categories such as
# `weekend_uplift_omitted`; the H1 evaluation maps those to the broader label vocabulary
# where appropriate (see CATEGORY_MAP in 08_evaluation.py). `unit_price_mismatch` is
# suppressed when a more specific rate-derived category already explains the same
# line's price delta, so it no longer double-counts against those categories.
#
# Confidence. Confidence values are deterministic audit-policy scores reflecting
# evidence quality and ambiguity; they are not probabilities. 08_evaluation.py reports
# confidence buckets descriptively on H1 rather than claiming statistical calibration
# from a 918-invoice development set alone.
