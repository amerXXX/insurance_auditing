# 11 — Reviewing the user's clause 11.4 duplicate-service check (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1

## User request

> Clause 11.4 means the same service cannot be billed twice for the same patient on the same service date—even across different invoices.
> Because billing descriptions are not yet matched to contract services, this cell finds obvious duplicate-description candidates first:
>
> ```python
> # Preliminary check for clause 11.4
> # Uses JSONL so reused invoice IDs do not mix line ownership
>
> import json
> import re
> import pandas as pd
> from IPython.display import display
>
> jsonl_path = DATA_DIR / "invoices" / "hospital_1_invoices.jsonl"
>
> duplicate_check_rows = []
>
> with jsonl_path.open(encoding="utf-8") as file:
>     for record_key, line in enumerate(file, start=1):
>         invoice = json.loads(line)
>
>         for item in invoice["line_items"]:
>             duplicate_check_rows.append({
>                 "record_key": record_key,
>                 "invoice_id": invoice["invoice_id"],
>                 "patient_id": invoice["patient_id"],
>                 "line_id": item["line_id"],
>                 "service_date": item["service_date"],
>                 "description": item["description"]
>             })
>
> duplicate_check = pd.DataFrame(duplicate_check_rows)
>
> # Parse dates in the temporary table
> duplicate_check["service_date_parsed"] = pd.to_datetime(
>     duplicate_check["service_date"],
>     format="%Y-%m-%d",
>     errors="coerce"
> )
>
> # Normalise wording only for an initial candidate check
> duplicate_check["service_key"] = (
>     duplicate_check["description"]
>     .str.lower()
>     .str.replace(r"/[a-z]{2}-\d+", "", regex=True)
>     .str.replace(r"[^a-z0-9 ]", " ", regex=True)
>     .str.replace(r"\s+", " ", regex=True)
>     .str.strip()
> )
>
> valid_dates = duplicate_check["service_date_parsed"].notna()
>
> duplicate_check["duplicate_count"] = 0
>
> duplicate_check.loc[valid_dates, "duplicate_count"] = (
>     duplicate_check.loc[valid_dates]
>     .groupby(
>         ["patient_id", "service_date_parsed", "service_key"]
>     )["line_id"]
>     .transform("size")
> )
>
> duplicate_candidates = duplicate_check[
>     duplicate_check["duplicate_count"] > 1
> ].copy()
>
> duplicate_candidates["flagged"] = 1
> duplicate_candidates["error_category"] = (
>     "duplicate_service_candidate"
> )
> duplicate_candidates["expected_total_status"] = (
>     "Review required"
> )
>
> duplicate_candidates["duplicate_scope"] = (
>     duplicate_candidates
>     .groupby(
>         ["patient_id", "service_date_parsed", "service_key"]
>     )["record_key"]
>     .transform("nunique")
>     .map(
>         lambda count:
>         "Across invoices" if count > 1
>         else "Within one invoice"
>     )
> )
>
> print("Duplicate-description candidates:",
>       len(duplicate_candidates))
>
> display(
>     duplicate_candidates[
>         [
>             "patient_id",
>             "service_date",
>             "description",
>             "invoice_id",
>             "line_id",
>             "duplicate_scope",
>             "flagged",
>             "error_category",
>             "expected_total_status"
>         ]
>     ]
> )
> ```
>
> This is only a preliminary check because different descriptions may refer to the same contracted service. After service matching, we should repeat the check using the canonical contract service name instead of `service_key`.

## What was checked

Ran the supplied code against the real data and cross-referenced the candidates against the `cross_invoice_duplicate` ground-truth label.

## Key findings

- Runs clean: 8 candidates / 4 pairs. Every one of the 4 ground-truth `cross_invoice_duplicate` invoices is captured, with no extra false candidates — perfect recall on this pass.
- But the ground truth is asymmetric: in all 4 pairs, only the invoice with the **later `invoice_date`** is labelled erroneous; the earlier one is labelled clean. The code as supplied flags both sides of every pair (`flagged = 1` for all 8 rows), which would produce 4 false positives if submitted as-is.
- Gave a rank-by-`invoice_date`-within-group fix to flag only the later occurrence.

## Status

Review of the user's own code, with a suggested fix given in-chat — not yet applied to any notebook file.

## Caveat carried forward

The "later invoice is the violation" rule is an inference from these 4 examples, not something clause 11.4 states explicitly — logged as a decision-log item, not a quoted contract rule.
