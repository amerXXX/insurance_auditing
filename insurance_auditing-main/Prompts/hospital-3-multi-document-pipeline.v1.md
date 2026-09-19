# Hospital 3 — multi-document, time-dependent pipeline (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 3, the last unattempted hospital; completes coverage of all four scored hospitals

## User request

> complete hospiatl 3

## What changed

A new `notebooks_py/hospital_3/` pipeline on the established numbered pattern. `main.py`
needed no change. With this, the combined scored `submission.csv` is **3,942 rows** —
exactly the "3942 invoices scored" the grading dashboard reports, i.e. complete coverage
of hospitals 2, 3, 4 and 5.

Hospital 3 is the contract the brief describes as "split across several documents", and it
is the only one whose rates change during the term:

- **Three instruments, with a stated precedence.** Base Agreement clause 1.3 requires the
  Base Agreement, Appendix B (rate schedule) and Amendment No. 1 to be read together, and
  fixes the order in a conflict: amendment over Appendix B, Appendix B over the Base
  Agreement. That says who wins a conflict but not whether one exists, so the documents are
  cross-checked against each other rather than trusted individually. Both checks pass: the
  amendment's "Rate to 31 December 2024" column restates Appendix B exactly for all seven
  substituted Services, and the Base Agreement's section 7 daily caps agree exactly with
  Appendix B's own daily-cap column. Had either disagreed, clause 1.3 would have decided
  it — but the disagreement itself would have been the finding to report.
- **Rates are time-dependent, by Service Date.** Amendment clause A1.1.1 takes effect
  1 January 2025 and A1.1.2 applies it "by Service Date", stating expressly that "The date
  on which an invoice is issued is irrelevant for this purpose"; Appendix B B.1 says the
  same from the other side. Roughly half the line items fall either side of that date
  (5,859 before / 5,789 after), so this is not a corner case — pricing everything from one
  rate table would misprice about half the invoices. Only the starting rate is
  date-dependent: A1.4.1 confirms the premiums, caps, bundles, exclusion windows and
  calculation conventions are unchanged and apply to the substituted rates exactly as they
  applied to the rates they replace.
- **Two Services were not contracted for the whole term.** A1.3 adds two Services billable
  only "in respect of Service Dates on or after 1 January 2025". Billing one against an
  earlier Service Date is billing something the Provider had no right to bill at all, so it
  is reported as `service_not_yet_contracted` and priced provisionally rather than at a
  rate that did not exist on that date.
- **A new error class the amendment creates.** Where a substituted-rate Service is billed
  at the rate from the other side of 1 January 2025 — a superseded rate billed late, or the
  new rate applied early — it is reported as `wrong_rate_period` rather than as a generic
  price mismatch, and the generic `unit_price_mismatch` is suppressed for that line.

## Validation

Hospital 3 has no labels, so it is validated internally:

| Check | Result |
|---|---|
| Clean invoices reconciling exactly (expected == billed) | **862 / 862 (100%)** |
| Same, invoices dated **before** the amendment | 402 clean, 100% |
| Same, invoices dated **on or after** the amendment | 400 clean, 100% |
| Same, invoices **spanning both** periods | 60 clean, 100% |
| Contracted services actually billed | **120 / 120** (0 never billed) |
| Distinct contracted rates | 127 (118 Appendix B + 7 substituted + 2 added) |
| Flagged invoices | 70 of 932 (7.5%) |
| Descriptions matched / resolved by price / left for review | 520 / 10 / 14 of 544 |

The period split is the check that matters: had the amendment's effective date been applied
wrongly, the post-2025 and mixed-period groups would have broken while the pre-2025 group
stayed clean. All three reconcile at 100% independently.

The 127-rate count independently matches the figure visible in the leaderboard's own
self-check message for this hospital ("127 rates checked against the invoices"), which is a
useful corroboration that the three documents were read as intended. That candidate's check
also reported "1 never billed"; ours reports 0 never billed, counting the 120 contracted
Services rather than the 127 distinct rates — the 7 pre-2025 rates that the amendment
supersedes are each billed, but a rate-level count would differ depending on whether a
superseded rate still counts as its own entry.

## Outcome

`notebooks_py/hospital_3/submission.csv` holds 932 rows. Combined scored `submission.csv`
is now 3,942 rows across all four scored hospitals, up from 3,010. Both Hospital 3-specific
categories fire on real data: `wrong_rate_period` on 4 invoices and
`service_not_yet_contracted` on 4.
