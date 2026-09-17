# 10 — Satisfying clause 5.1's aggregate-quantity requirement (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1

## User request

> how this is satsfied A threshold premium is assessed against the aggregate quantity of that Service delivered to the Patient on the Service Day, not against the quantity on any one line item.

## What was checked

Searched for cases where the same patient billed the same service on the same day across more than one line item.

## Key finding

Rare (4 of 11,544 patient+date+service groups) but real — and one case splits across **two different invoices** (`INV-H1-000246` and `INV-H1-000852`, same patient, same day), each individually under any threshold, aggregate above it. This is exactly the scenario 5.1 exists to prevent someone gaming.

## What was given

```python
lines['aggregate_daily_qty'] = (
    lines.groupby(['patient_id', 'service', 'service_date'])['quantity']
         .transform('sum')
)
premium_applies = lines['aggregate_daily_qty'] > lines['threshold_qty']
```

With three correctness requirements: group by `patient_id` + `service_date` (not `invoice_id`, which would miss the cross-invoice case); use `transform` so the aggregate is copied back to every line in the group; group by `service` not raw `description` once Phase 3 exists (using `description` as a proxy under-counts whenever the same service is billed under two different wordings the same day).

## Status

Demonstration and code given in-chat; not yet added to `main.ipynb` (depends on Phase 3's service mapping to be fully correct).

## Caveat carried forward

Logged as an open assumption: whether "Patient" scope should also require the same `contract_number`/hospital — moot for Hospital 1 (single hospital) but flagged in case hospitals 2-5 ever share patients.
