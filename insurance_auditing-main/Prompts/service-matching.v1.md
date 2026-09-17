# 11 — Service matching (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1, step 2 of roadmap — **superseded by v2**

## Problem

`description` is free text and heavily abbreviated:
`"Procedure Routine Urologic Biop /NG-3022"` → `"Routine Urologic Biopsy Procedure"`,
with a trailing reference code carrying no service information.

## Approach

1. Strip trailing `/NG-####` reference codes.
2. Score candidates: exact word match > prefix match (`"onc"` → Oncology) >
   in-order letter-subsequence match (`"rtn"` → Routine), greedy best-pairing.
3. Manual fixups for two abbreviations that do not decompose algorithmically:
   `"ent"` → otolaryngologic, `"gi"` → gastrointestinal.
4. Tie-break near-equal candidates using the billed `unit_price_cents`.

## Result

488 unique descriptions: 463 matched, 16 resolved by price, 9 unresolved.

## Why superseded

The 9 unresolved were carried straight through to `flagged=1`,
`error_category="unknown_service"`, on the basis that all 9 sat on invoices
labelled `unknown_service`. That is label-fitting, and it auto-marks unmatched
descriptions as errors — both prohibited by the ground rules in prompt 09.
