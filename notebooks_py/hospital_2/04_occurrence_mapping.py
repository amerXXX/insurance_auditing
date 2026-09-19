# Hospital 2 pipeline, part 4/7 — depends on parts 1-3
# (uses line_items, invoices).

### Occurrence mapping for reused invoice IDs
#
# Clause 13.6 requires each invoice to be identified by an invoice number unique across
# the whole term; Hospital 2 reuses some invoice IDs across two genuinely different
# transactions each (the same pattern as Hospitals 1, 4 and 5). The line-ID group prefix
# (H2-Lnnnnn-nn) identifies the original transaction group, which is mapped
# chronologically onto the invoice-table occurrences so a reused ID's two transactions are
# priced independently rather than merged.

line_items["line_group_num"] = (
    line_items["line_id"].astype(str)
    .str.extract(r"^H2-L(\d+)-", expand=False)
    .astype("Int64")
)
if line_items["line_group_num"].isna().any():
    raise ValueError("Unable to recover line-group identity from one or more line IDs")

invoices["_row_order"] = range(len(invoices))
invoices["occurrence_rank"] = (
    invoices.sort_values(["invoice_id", "invoice_date", "_row_order"])
    .groupby("invoice_id").cumcount()
)

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

# discharge_date travels with the occurrence: clause 13.1 measures the submission window
# from the discharge date of the Episode of Care the invoice relates to.
occ_cols = ["invoice_id", "occurrence_rank", "invoice_date", "patient_id",
            "facility_code", "plan_tier", "contract_number", "invoice_total_cents",
            "admission_date", "discharge_date"]
line_items = line_items.merge(
    invoices[occ_cols], on=["invoice_id", "occurrence_rank"], how="left",
    validate="many_to_one", suffixes=("", "_invoice"),
)

line_items["invoice_occurrence_key"] = (
    line_items["invoice_id"].astype(str) + "::" + line_items["occurrence_rank"].astype(str)
)
