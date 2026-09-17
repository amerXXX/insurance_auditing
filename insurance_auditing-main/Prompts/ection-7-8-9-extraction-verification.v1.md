# 9 — Verifying the Section 7/8/9 extraction against the contract text (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1

## User request

> [image upload: three tables — §7 volume discounts (11 rows), §8 daily caps (7 rows), §9 bundled services (3 rows), each with a `source_line` column]
>
> are these calid results based on contract ?

## What was checked

Cross-referenced every row and every `source_line` value in the three tables against the raw contract text.

## Key finding

All 21 rows across the three tables match exactly, including every `source_line` reference (§7: lines 188–198, §8: lines 207–213, §9: lines 219–221).

## Note (not an error)

`discount_percent` is stored as a plain number (`10`, `25`, ...) rather than a fraction — needs dividing by 100 when it feeds §3.2's pricing formula.

## Status

Verification only — the tables were the user's own extraction output, confirmed correct as supplied.
