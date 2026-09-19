# Hospital 5 pipeline, part 4/7 — depends on parts 1-3
# (uses line_items, invoices).

### Occurrence mapping for reused invoice IDs
#
# Clause 10.1 requires an invoice number unique across the term; Hospital 5 reuses some
# invoice IDs across two genuinely different transactions each (the same pattern as
# Hospitals 1 and 4). The line-ID group prefix (H5-Lnnnnn-nn) identifies the original
# transaction group, which is mapped chronologically onto the invoice-table occurrences
# so a reused ID's two transactions are priced independently rather than merged.

# Preserve original line-group identity. Synthetic Hospital 5 line IDs retain the
# transaction group even when an invoice identifier is accidentally reused.
line_items["line_group_num"] = (
    line_items["line_id"].astype(str)
    .str.extract(r"^H5-L(\d+)-", expand=False)
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

line_items = line_items.merge(
    group_meta[["invoice_id", "line_group_num", "group_rank", "group_billed_total_cents"]],
    on=["invoice_id", "line_group_num"], how="left",
)
line_items["occurrence_rank"] = line_items["group_rank"].astype(int)

# The facility code and plan tier travel with the invoice occurrence: clause 1.2 ties the
# facility multiplier to the facility recorded for the line, and clause 1.3 applies the
# invoice's plan tier to every line item on that invoice.
occ_cols = ["invoice_id", "occurrence_rank", "invoice_date", "patient_id",
            "facility_code", "plan_tier", "contract_number", "invoice_total_cents"]
line_items = line_items.merge(
    invoices[occ_cols], on=["invoice_id", "occurrence_rank"], how="left",
    validate="many_to_one", suffixes=("", "_invoice"),
)

line_items["invoice_occurrence_key"] = (
    line_items["invoice_id"].astype(str) + "::" + line_items["occurrence_rank"].astype(str)
)
