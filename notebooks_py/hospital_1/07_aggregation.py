# Hospital 1 pipeline, part 7/9 — depends on parts 1-6
# (uses line_items, invoices, LINE_CHECK_COLS).

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

# Occurrence-specific line checks.
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

# Explicit invoice-total arithmetic mismatch.
occ_summary["invoice_total_mismatch"] = (
    occ_summary["billed_line_total_sum_cents"] != occ_summary["invoice_total_cents"]
)

# Duplicate invoice IDs: the development-set convention is to report the later invoice occurrence.
latest_rank = occ_summary.groupby("invoice_id")["occurrence_rank"].transform("max")
occ_summary["selected_occurrence"] = occ_summary["occurrence_rank"] == latest_rank

# Error categories are deliberately specific. Unknown service is a real audit flag and remains
# separate from the provisional expected-total calculation.
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

# Collapse to one row per invoice ID. For duplicates this deliberately selects the later occurrence.
invoice_summary = occ_summary[occ_summary["selected_occurrence"]].copy()
invoice_summary = invoice_summary.sort_values(["invoice_id"]).reset_index(drop=True)

# Unmatched descriptions are flags, but the expected amount for those lines is provisional.
invoice_summary["billed_total_cents"] = invoice_summary["invoice_total_cents"]
invoice_summary["expected_total_cents"] = invoice_summary["expected_total_cents"].round().astype("Int64")

print("Flagged counts:", invoice_summary["flagged"].value_counts().to_dict())
print("Confidence distribution:", invoice_summary["confidence"].value_counts().sort_index().to_dict())
print("Invoices with provisional expected totals:", int(invoice_summary["any_provisional_expected"].sum()))
