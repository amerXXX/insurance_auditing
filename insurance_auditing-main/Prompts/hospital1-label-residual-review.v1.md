# Hospital 1 — label-residual review and targeted fixes (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1, post-hoc review of `hospital_1_dev_predictions.csv` against `labels/hospital_1_labels.csv`, working from the split pipeline in `notebooks_py/hospital_1/`

## User request

> when i ask you we nned to work on thos C:\Users\AMER\Downloads\17Sep\notebooks_py\hospital_1\01_setup.py
> C:\Users\AMER\Downloads\17Sep\notebooks_py\hospital_1\02_contract_extraction.py
> C:\Users\AMER\Downloads\17Sep\notebooks_py\hospital_1\03_matching_functions.py
> C:\Users\AMER\Downloads\17Sep\notebooks_py\hospital_1\04_occurrence_mapping_and_matching.py
> C:\Users\AMER\Downloads\17Sep\notebooks_py\hospital_1\05_checks.py
> C:\Users\AMER\Downloads\17Sep\notebooks_py\hospital_1\06_pricing.py
> C:\Users\AMER\Downloads\17Sep\notebooks_py\hospital_1\07_aggregation.py
> C:\Users\AMER\Downloads\17Sep\notebooks_py\hospital_1\08_evaluation.py
> C:\Users\AMER\Downloads\17Sep\notebooks_py\hospital_1\09_output.py

Supplied alongside this: a detailed external write-up (not authored by this assistant)
diagnosing the 5 `expected_total_cents` residuals between `hospital_1_dev_predictions.csv`
and the labels, and proposing four fixes — (1) raise `MIN_SCORE`/`GAP_THRESHOLD`, (2) add a
unit-basis veto to the matcher, (3) a hypothesis for the daily-cap discrepancy involving
cross-invoice cumulative counts, and (4) suppress `unit_price_mismatch` when a rate-derived
category already fires on the same line.

## What changed

Before applying anything, each of the four proposed fixes was independently re-derived
against the actual data rather than taken on trust:

- **Fix (1), threshold tightening — rejected.** Tested `MIN_SCORE 0.55→0.65` /
  `GAP_THRESHOLD 0.08→0.12` against all 488 matched descriptions. The target case
  (`Fract Outpatient Radiotherapy`, score 0.736, gap 0.315) still clears the tighter bar —
  the fix would not even have changed the outcome it was proposed for — while it demotes
  two other, genuinely-correct matches (`Immun Consult Outpatient`, `Emer Ortho`) to
  `needs_review`. Not applied.
- **Fix (2), unit-basis veto on the matcher — rejected.** `INV-H1-000236`'s bad match is
  already one of 12 lines the pipeline flags `wrong_unit_basis`; 11 of those 12 are
  genuinely correct matches billed on a wrong unit (real injected errors, currently
  detected at recall 1.0, precision 0.917). A hard veto on unit mismatch inside the matcher
  would reject the correct candidate on all 11 of those too, destroying that detection
  category. Not applied. A narrower "no clinical-specialty word at all in the description"
  veto was also tested and rejected: it affects 51 descriptions, 27 of which trace to `ren`
  and `onc` never being expanded by `TOKEN_ALIASES` (see fix below), and the remaining 24
  are legitimately anchor-less descriptions that are currently matched correctly — net
  harmful.
- **Fix (3), daily-cap hypothesis — investigated, not resolved, not hacked around.** Traced
  all four daily-cap residuals (`INV-H1-000015/049/227/725`) against every line for the
  same patient+service+date across the *entire* dataset (ruling out cross-invoice
  cumulative counts — each is the only line for that patient+service+date) and against the
  contract's Section 8 text directly (no interpretive clause exists; it is a bare table).
  Backed out the implied "label-correct" billable quantity precisely for the three
  uncorrelated cases: all three independently imply exactly **3 units**, regardless of the
  service's stated cap (4, 12, 8) or the billed quantity (9, 14, 11). No formula or contract
  clause reproduces this. Documented as a likely artifact of how the synthetic test data
  was generated (a fixed true quantity inflated to trigger the cap check), not a
  discoverable audit rule. Not hacked in — see ground rule 2 (`09-remaining-work-roadmap`
  in this repository's own prior record / rule 2 of `Master-Prompt.md`): do not force
  predictions to match every label.
- **Fix (4), suppress redundant `unit_price_mismatch` — verified and applied.** 18 of 39
  lines currently flagged `unit_price_mismatch` also carry a more specific rate-derived
  category (`premium_*`, `weekend_uplift_*`, `volume_discount_*`) on the same line.
  Re-ran the full aggregation + evaluation with the suppression applied: category F1 for
  `unit_price_mismatch` goes from 0.540 (precision 0.370, recall 1.000) to 0.720
  (precision 0.600, recall 0.900); invoice-level `flagged` accuracy/precision/recall/F1 is
  unchanged at 1.000 (the change is to descriptive category text only, not to
  `expected_total_cents`). Applied in `06_pricing.py`.
- **Independent finding, applied alongside (4):** `ren`→`renal` and `onc`→`oncology` were
  missing from `TOKEN_ALIASES`, so the anchor-conflict safety net could not check for
  renal/oncology specialty conflicts at all on any description using those very common
  abbreviations. Re-tested match outcomes for all 488 descriptions before/after adding
  both aliases: the top-matched service and `matched`/`needs_review` status are identical
  in every case; only the confidence margin (score/gap) increases, because previously-
  invisible anchor conflicts against sibling specialties are now correctly penalised.
  Zero regressions. Applied in `03_matching_functions.py`.

## Outcome

`hospital_1_dev_predictions.csv` regenerated with both applied fixes:

| Metric | Before | After |
|---|---|---|
| Invoice-level accuracy / precision / recall / F1 | 1.000 / 1.000 / 1.000 / 1.000 | unchanged |
| `unit_price_mismatch` category (precision / recall / F1) | 0.370 / 1.000 / 0.540 | 0.600 / 0.900 / 0.720 |
| `expected_total_cents` residuals | 5 invoices | unchanged (5 invoices) |

The 5 `expected_total_cents` residuals (4 daily-cap, 1 matcher edge case on
`INV-H1-000236`) remain, disclosed rather than engineered away. `wrong_unit_basis`
precision remains 11/12 for the same reason.
