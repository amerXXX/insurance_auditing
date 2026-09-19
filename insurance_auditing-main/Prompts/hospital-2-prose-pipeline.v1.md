# Hospital 2 — prose-contract pipeline (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 2, built end to end after Hospitals 4 and 5, prompted by leaderboard feedback

## User request

> be carefull about the cost and strart Hospital 2

Supplied alongside this: screenshots of the grading dashboard showing the candidate's own
row (#26) and the top three. Two facts from those screenshots drove the approach.

## What the leaderboard changed

**The cost function is asymmetric.** "Ranked by cost-weighted score — a false negative
costs 5× a false positive, so lower is better." The method had been calibrated on
Hospital 1 for precision (1.000/1.000 there), but the score punishes *missed* erroneous
invoices five times harder than over-flagging. With hospitals 2 and 3 contributing roughly
half the scored invoice pool and carrying zero predictions, every erroneous invoice in
them was a 5× penalty. Attempting Hospital 2 was therefore the single highest-value action
available, ahead of any further tuning of the hospitals already covered.

**A perfect score is achievable.** The top three candidates sit at cost 0 — F1 1.000,
precision 1.000, recall 1.000, decoy FP 0.0% — across all four scored hospitals. So the
contracts are fully determinate, and the winners are not hedging with review queues; they
resolve every description. One of them aborts rather than emit output it cannot vouch for
("stopped by its own check: 187 rules checked against the text, 0 not found; 127 rates
checked against the invoices, 1 never billed"). That completeness-assertion standard was
adopted here.

**A check against the Hospital 1 labels corrected a misreading.** Twelve H1 invoices have
a Service Date after their invoice date, but only five carry
`service_date_after_invoice_date` in the labels — which looked like seven decoys. Reading
the labels properly shows all twelve are `is_erroneous = 1`; the other seven simply carry a
different category name. Since the brief makes `error_category` free text and scores only
the binary `flagged`, a category mismatch costs nothing and only the flag matters. That
removed the case for suppressing those flags and confirmed the existing check set is
decoy-safe as calibrated (H1 precision 1.000, zero false positives).

## What changed

A new `notebooks_py/hospital_2/` pipeline on the established numbered pattern. `main.py`
needed no change — it discovers `hospital_*` folders automatically.

Hospital 2 is the prose contract. Clause 1.4 states the rates "are not gathered into a
single schedule"; the front matter states "No tables are used in this instrument". Every
rate, unit basis, daily cap, threshold premium, non-business-day uplift, cumulative volume
discount and bundle is embedded in legal sentences, with figures written in words and
repeated in brackets ("twenty-four (24)", "thirty percent (30%)"), spread across thirteen
"Contracted Services (N Group)" Articles interleaved with unrelated boilerplate Articles
(Notices, Audit Rights, Confidentiality, Force Majeure, ...).

- **Extraction is asserted, not assumed.** Every provision count parsed is reconciled
  against the number of times its phrase occurs in the raw text: 76 services (76 "at the
  rate of GBP"), 8 daily caps, 9 threshold premiums, 8 non-business-day uplifts, 12
  discount tiers, 6 bundle sentences (3 unordered pairs). An unrecognised clause fails the
  run rather than silently dropping a contract rule.
- **Two provisions are genuinely absent**, verified by searching the full text for every
  wording the other three agreements use, and asserted so a future revision cannot
  reintroduce them silently: Hospital 2 defines **no exclusion windows** and contains **no
  prohibition on billing the same Service twice** for the same Patient and Service Date.
  Hospitals 1, 4 and 5 all zero out a later duplicate; doing so here would invent a term
  this Provider never agreed to, so repeats are priced normally and not flagged.
- **Both multipliers are the identity** (clause 1.3: single facility, "No facility
  differential applies", rates apply "irrespective of the Patient's plan tier"), so stages
  (b) and (c) are skipped rather than applied as 1× multiplications.
- **A new check type:** clause 13.1 requires submission within sixty days of the discharge
  date of the Episode of Care. It is wired into the prediction and is clean on this data
  (the latest invoice is ten days after discharge).
- **Article XIII is fifteen clauses restating three rules** (13.1 submission window, 13.6
  unique invoice number, 13.11 contract number). The remaining twelve restate each as an
  effectiveness condition, a good-faith obligation, a waiver carve-out and an
  avoidance-of-doubt carve-out, adding no further testable condition, so each rule is
  checked once rather than fifteen times.

## Validation

Hospital 2 has no labels, so it is validated internally:

| Check | Result |
|---|---|
| Clean invoices reconciling exactly (expected == billed) | **1,050 / 1,050 (100%)** |
| Provision counts reconciled against raw contract text | all 6 categories exact |
| Contracted rates actually billed somewhere in the data | **76 / 76** (0 never billed) |
| Flagged invoices | 75 of 1,125 (6.7%) |
| Descriptions matched / resolved by price / left for review | 475 / 17 / 14 of 506 |

## Outcome

`notebooks_py/hospital_2/submission.csv` holds 1,125 rows. The combined scored
`submission.csv` is now 3,010 rows across hospitals 2, 4 and 5 (was 1,885). Against the
dashboard's stated 3,942 scored invoices, the remaining gap is roughly 932 — Hospital 3,
the only one still unattempted.
