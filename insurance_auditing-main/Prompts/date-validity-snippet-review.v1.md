# 4 — Reviewing the user's date-validity snippet (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1

## User request

> ```notebook-python
> for column in ["invoice_date", "admission_date", "discharge_date"]:
>     invoices[column] = pd.to_datetime(invoices[column], errors="coerce")
> lines["service_date"] = pd.to_datetime(lines["service_date"], errors="coerce")
>
> print("Unusable invoice dates:", invoices["invoice_date"].isna().sum())
> print("Unusable service dates:", lines["service_date"].isna().sum())
> print("Invoice dates:", invoices["invoice_date"].min(), "to", invoices["invoice_date"].max())
> print("Service dates:", lines["service_date"].min(), "to", lines["service_date"].max())
> print("Patients:", invoices["patient_id"].nunique())
> print("Distinct raw descriptions:", lines["description"].nunique())
> display((invoices["invoice_total_cents"] / 100).describe().to_frame("Invoice amount (GBP)"))
> ```

## What was checked

Ran the snippet as supplied (with `lines` = `hospital_1_line_items.csv`) against the real data.

## Key finding

Runs clean. 0 unusable invoice dates, 6 unusable service dates — matches the `malformed_service_date` label category count exactly. Service dates span 2022-12-30 to 2026-07-24, well outside the 2024-01-01–2025-12-31 contract term. 226 unique patients.

## Status

This was the user's own code, run for verification — no notebook change made by the assistant.
