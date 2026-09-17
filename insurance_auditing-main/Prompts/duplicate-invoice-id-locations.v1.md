# 3 — Locating the duplicated invoice_id rows (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1

## User request

> i did not understand the issue of  duplicated invoice_id : 5 where they are

## What was checked

Filtered `hospital_1_invoices.csv` for `invoice_id` values appearing more than once.

## Key finding

5 `invoice_id` values are each reused across two entirely unrelated invoices — different patients, dates, and totals. Confirmed against clause 11.2 ("An identifier may not be reused"): this is the violation itself, not messy data to clean up.

One of the five pairs (`INV-H1-000152`) also carries a second, independent problem: its second occurrence has `contract_number: INS-H4-2024-2049` — a Hospital 4 contract number on a Hospital 1 invoice.

## Status

Investigation only, no notebook change at this point.
