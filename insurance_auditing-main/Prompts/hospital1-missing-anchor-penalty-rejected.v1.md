# Hospital 1 — missing-anchor score penalty (v1, rejected)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1, follow-up to `hospital1-label-residual-review.v1.md` — a second, more
targeted attempt at the `INV-H1-000236` matcher limitation documented there

## User request

> waht do you think of 2. The Matcher Limitation (INV-H1-000236) — How to fix itYou noted
> that the description "Fract Outpatient Radiotherapy" falsely matched to "Outpatient
> Metabolic Radiotherapy Fraction" (rate: 22,775), resulting in a user-expected line total
> of 68,325. Because the label rightly flagged this anchorless line as unknown_service, it
> kept the provisional billed line total (24,675) — creating an exact difference of 43,650
> cents. You mentioned that tightening your MIN_SCORE or unit-basis broke other valid
> matches. The real root cause lies in your candidate_conflict function in
> 03_matching_functions.py. Currently, you penalize conflicting anchors (e.g., Cardiac vs.
> Renal) with d_anchor.isdisjoint(s_anchor). However, because "Fract Outpatient
> Radiotherapy" has no clinical specialty word, d_anchor is an empty set. When d_anchor is
> empty, anchor_conflict evaluates to False, allowing the match to skate by purely on
> overlapping generic words without any penalty for missing a mandatory clinical anchor.
> The Fix: You can introduce a missing_anchor penalty. If the contract service requires an
> anchor (s_anchor exists) but the billed description provides none (d_anchor is empty),
> apply a targeted penalty. [supplied a full code diff to `candidate_conflict` and
> `match_description` in `03_matching_functions.py`: add `missing_anchor = bool(s_anchor
> and not d_anchor)`, subtract 0.30 from the score when true] By subtracting 0.30
> specifically for a missing anchor, the score for "Outpatient Metabolic Radiotherapy
> Fraction" will drop well below your MIN_SCORE of 0.55. This cleanly pushes the line to
> unknown_service (matching the ground truth label perfectly) without harming any of your
> fuzzy matching logic for typos or abbreviation mismatches!

## What changed

Nothing in the pipeline. The proposed diff was tested against the real Hospital 1 data
(with the already-applied `ren`/`onc` alias fix and `unit_price_mismatch` suppression from
`hospital1-label-residual-review.v1.md` in place) before touching any file — not applied
on the strength of the reasoning alone.

Two tests:

1. **Blast radius across all 488 descriptions.** Applying `-0.30` when a candidate's
   `s_anchor` is non-empty but the description's `d_anchor` is empty flips 17 descriptions
   from a confident `matched` status to `needs_review` (down from 51 in an earlier, blunter
   version of this same idea, before the `ren`/`onc` alias fix closed most of the gap — see
   `hospital1-label-residual-review.v1.md`). `Fract Outpatient Radiotherapy` (the target
   case) does correctly drop from score 0.736 to 0.436, below `MIN_SCORE`.
2. **Full pipeline re-run against the labels.** This is the test that mattered. Re-ran
   Hospital 1 end to end (occurrence mapping through aggregation) with the penalty applied:

   | Metric | Before | With the penalty |
   |---|---|---|
   | Precision | 1.000 | **0.552** |
   | Recall | 1.000 | 1.000 |
   | False positives | 0 | **47** |
   | `expected_total_cents` residuals | 5 invoices | 5 invoices (one swapped for another) |

   The penalty does fix `INV-H1-000236` — it now shows `daily_cap_exceeded|unknown_service`
   instead of the wrong radiotherapy match — but at the cost of 47 previously-correct
   invoices now wrongly flagged as erroneous, because many of this contract's service names
   legitimately carry a specialty word (`Renal`, `Cardiac`, `Rheumatologic`, ...) that a
   billing description abbreviates away without losing genuine identifiability (e.g. `Rtn
   Biop Proc` → `Routine Urologic Biopsy Procedure` is a correct match despite never stating
   "urologic"). The penalty cannot distinguish that case from `INV-H1-000236`'s actual
   problem — a generic setting word (`Outpatient`) coincidentally overlapping exactly one
   candidate with no specialty confirmation at all. Both present as "no anchor in the
   description," but only one is genuinely unsafe to match.

## Outcome

**Rejected.** Not applied to `03_matching_functions.py` or anywhere else. The exercise
scores on precision and explicitly treats a confidently wrong flag as worse than a
disclosed uncertainty (see the exercise brief, "A confidently wrong extraction is worse
than a flagged uncertainty"); trading 0 false positives for 47 to resolve one
already-documented, already-accepted residual affecting 0.5% of invoices is a clear net
loss under that standard. `INV-H1-000236` remains a documented limitation in the decision
log at the end of `notebooks_py/hospital_1/09_output.py` — not hacked around a second time
with a smaller hammer.
