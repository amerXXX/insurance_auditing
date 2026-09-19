# Hospital 1 pipeline, part 4/9 — depends on parts 1-3
# (uses line_items, invoices, rate_schedule, match_description, plausible_unit_prices).

# Resolve descriptions, then assign line groups to invoice occurrences.
# The occurrence mapping prevents reused invoice IDs from doubling line items.

# Preserve original line-group identity. Synthetic Hospital 1 line IDs retain the
# transaction group even when an invoice identifier is accidentally reused.
line_items["line_group_num"] = (
    line_items["line_id"].astype(str)
    .str.extract(r"^H1-L(\d+)-", expand=False)
    .astype("Int64")
)

if line_items["line_group_num"].isna().any():
    raise ValueError("Unable to recover line-group identity from one or more line IDs")

# Invoice occurrence rank: chronological within reused invoice IDs.
invoices["_row_order"] = range(len(invoices))
invoices["occurrence_rank"] = (
    invoices.sort_values(["invoice_id", "invoice_date", "_row_order"])
    .groupby("invoice_id").cumcount()
)

# Line-group rank: chronological source-group order.
group_meta = (
    line_items.groupby(["invoice_id", "line_group_num"], dropna=False)
    .agg(group_billed_total_cents=("line_total_cents", "sum"),
         group_min_service_raw=("service_date", "first"))
    .reset_index()
)
group_meta["group_rank"] = (
    group_meta.sort_values(["invoice_id", "line_group_num"])
    .groupby("invoice_id").cumcount()
)

# Map each group rank to the invoice occurrence rank. Non-duplicate IDs simply get 0.
line_items = line_items.merge(
    group_meta[["invoice_id", "line_group_num", "group_rank", "group_billed_total_cents"]],
    on=["invoice_id", "line_group_num"], how="left", suffixes=("", "_group")
)
line_items["occurrence_rank"] = line_items["group_rank"].astype(int)

occ_cols = ["invoice_id", "occurrence_rank", "invoice_date", "patient_id",
            "facility_code", "plan_tier", "contract_number", "invoice_total_cents"]
line_items = line_items.merge(
    invoices[occ_cols], on=["invoice_id", "occurrence_rank"], how="left",
    validate="many_to_one", suffixes=("", "_invoice")
)

# Per-description matching. No billed-price tie-break is allowed unless text/structure
# leaves compatible candidates and exactly one has a plausible observed unit price.
observed_prices = (
    line_items.groupby("description")["unit_price_cents"]
    .apply(lambda s: set(int(x) for x in s.unique()))
)

match_records = []
for desc in line_items["description"].dropna().astype(str).unique():
    top = match_description(desc, rate_schedule, top_k=8)
    top1, top2 = top[0], top[1] if len(top) > 1 else None
    gap = top1["score"] - (top2["score"] if top2 else 0.0)
    obs = observed_prices.get(desc, set())

    structurally_compatible = [
        r for r in top
        if not r["anchor_conflict"] and not r["class_conflict"]
    ]

    status = "needs_review"
    chosen = None
    reason = ""

    # Strong, separated text match.
    if (not top1["anchor_conflict"] and not top1["class_conflict"]
            and top1["score"] >= MIN_SCORE and gap >= GAP_THRESHOLD):
        status, chosen = "matched", top1["service"]
        reason = "strong_text_match"
    else:
        # Secondary price evidence is allowed only among structurally compatible candidates.
        close = [r for r in structurally_compatible if r["score"] >= max(top1["score"] - GAP_THRESHOLD, 0)]
        consistent = [r for r in close if obs and obs.issubset(plausible_unit_prices(r["service"]))]
        if len(consistent) == 1 and consistent[0]["score"] >= 0.35:
            status, chosen = "resolved_by_price", consistent[0]["service"]
            reason = "secondary_price_support"
        else:
            if top1["anchor_conflict"]:
                reason = "clinical_anchor_conflict"
            elif top1["class_conflict"]:
                reason = "service_class_conflict"
            elif len(structurally_compatible) > 1:
                reason = "ambiguous_text_match"
            else:
                reason = "insufficient_text_evidence"

    match_records.append({
        "description": desc,
        "matched_service": chosen,
        "text_score": round(top1["score"], 3),
        "gap": round(gap, 3),
        "match_status": status,
        "match_reason": reason,
        "top_candidates": str([(round(r["score"], 3), r["service"]) for r in top[:3]]),
    })

description_matches = pd.DataFrame(match_records)

# Attach matching to line items.
line_items = line_items.merge(
    description_matches[["description", "matched_service", "match_status", "match_reason"]],
    on="description", how="left", validate="many_to_one"
)

line_items["service_date_raw"] = line_items["service_date"]
line_items["service_date"] = pd.to_datetime(
    line_items["service_date_raw"], format="%Y-%m-%d", errors="coerce"
)

# A stable occurrence key is useful for aggregation and debugging.
line_items["invoice_occurrence_key"] = (
    line_items["invoice_id"].astype(str) + "::" + line_items["occurrence_rank"].astype(str)
)
