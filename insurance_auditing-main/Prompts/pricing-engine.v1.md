# 13 — Pricing engine (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1, step 4 of roadmap

## Task

Apply clause 3.2 order: `bundle → facility → plan → premium → weekend uplift →
volume discount → quantity`, with half-up rounding after **each** step (3.1).

## Bug found and fixed

Joining `line_items` to `invoices` on `invoice_id` to obtain `patient_id`
**silently duplicated rows** wherever an invoice ID was reused (11,415 → 11,548
rows). Those phantom rows corrupted every per-patient/per-day grouping and, worse,
the hospital-wide cumulative volume-discount running count for every service
sorted after them. Fixed by joining against a de-duplicated copy.

The reused IDs are still caught by the 11.2 check; only the join is de-duplicated.

## Assumptions logged

* **Threshold premium:** once a patient/service/day aggregate exceeds the threshold,
  the uplift applies to **every** unit that day — contrast volume discounts, which
  the contract explicitly limits to "subsequent units".
* **Volume discount:** cumulative utilisation is hospital-wide across all patients,
  in service-date then ascending-`line_id` order.
* **Untested path:** no Hospital 1 service is subject to both a threshold premium
  and a weekend uplift, so the premium-then-uplift ordering is never exercised here.

## Validation

All **855** labelled-correct invoices reproduce their billed total exactly (100%).
