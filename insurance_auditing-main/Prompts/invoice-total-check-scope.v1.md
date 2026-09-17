# 2 — Scope of the invoice_total == sum(line_items) check (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1

## User request

> do we look only for invoice_total_cents = line_total_cents ( for every line_itmes) or there is other factors we need to considered
>
> answer simply please and be specific 

## Answer given

That check only catches arithmetic errors (`line_total_arithmetic`, `invoice_total_mismatch`). It misses:

- mispriced line items (wrong rate, unit basis, multiplier, premium, discount, bundle)
- contract-rule violations (daily caps, exclusion windows, missed/misapplied premiums)
- structural issues (duplicate invoice IDs, cross-invoice duplicates, bad service dates, unmatched service descriptions, wrong contract number)

No code was run or changed in this exchange — conceptual answer only, drawing on the label-category breakdown already produced in record 1.

## Status

No artifact change.
