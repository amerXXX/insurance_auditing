# Hospital 5 — full pipeline (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 5, built end to end on the established per-hospital pattern

## User request

> can you implment Hospital 5 ? from edn to end

## What changed

A new `notebooks_py/hospital_5/` pipeline in the same numbered pattern as Hospitals 1 and
4 (`01_setup` → `02_contract_extraction` → `03_service_matching` →
`04_occurrence_mapping` → `05_checks` → `06_pricing` → `07_aggregation_output`).
`main.py` required no change — it discovers `hospital_*` folders automatically, which is
what that pattern was built for.

Hospital 5's agreement differs from both earlier contracts in ways that had to be
re-derived rather than assumed:

- **The rate tables are supplied twice** — inline in the Markdown agreement, and again as
  `network_reimbursement_agreement_rate_tables.pdf`. No PDF library was available, so the
  PDF's ASCII85+Flate streams were decoded with the standard library and its Tables 1–3
  compared value-by-value against the Markdown *before* any pipeline code was written. All
  84 services agree exactly on unit basis, base rate, daily cap, all three facility
  multipliers and all three plan-tier multipliers. The Markdown is therefore parsed as the
  single source of truth and the PDF treated as a redundant rendering. (A first version of
  that comparison reported 67 spurious mismatches; the cause was the comparison script
  itself matching each service name against the first table it appeared in, not the
  contract. Scoping each search to its own table region cleared it. The check was
  re-verified before being trusted.)
- **Facility and plan-tier multipliers do real work for the first time.** Tables 2 and 3
  vary the rate per service across F-MAIN/F-NORTH/F-COAST and BRONZE/SILVER/GOLD; both
  were structurally 1× for Hospitals 1 and 4. The pricing engine gains stages (b) and (c)
  accordingly, with `Decimal` arithmetic and half-up rounding after each step per clause
  3.2.
- **Daily caps live in Table 1**, not a section of their own as in Hospital 1.
- **Two new error categories**, `facility_multiplier_misapplied` and
  `plan_tier_multiplier_misapplied`, reported when the billed unit price matches the chain
  run under a different facility or tier than the invoice records. Both are treated as
  corrective-rate categories for confidence, and the generic `unit_price_mismatch` is
  suppressed when either fires (the same subordination rule applied to Hospitals 1 and 4).
- **Unknown facility code / plan tier are wired into the prediction**, not left as
  diagnostics: each selects a mandatory multiplier, so a line carrying a value outside the
  contract's closed sets cannot be priced at all. Both are clean on the supplied data.
- **`plausible_unit_prices()` had to model the multipliers.** It is used only to break a
  text tie between structurally-compatible candidates; built from unmultiplied rates it
  would have matched nothing on Hospital 5 and the tie-break would have been silently
  inert. It now spans every facility × tier combination, and the service's bundled
  substituted rate too — closing the gap Hospitals 1 and 4 recorded as a known limitation.

## Validation

Hospital 5 has no labels, so the pipeline was validated internally rather than scored:

| Check | Result |
|---|---|
| Invoices reported clean that reconcile exactly (expected == billed) | **974 / 974 (100%)** |
| Same, broken down by facility (F-MAIN / F-NORTH / F-COAST) | 100% / 100% / 100% |
| Same, broken down by plan tier (BRONZE / SILVER / GOLD) | 100% / 100% / 100% |
| Flagged invoices | 76 of 1050 (7.2%) |
| Descriptions matched / resolved by price / left for review | 453 / 9 / 12 of 474 |

The per-facility and per-tier breakdown is the check that matters: a mismapped multiplier
column would leave F-MAIN (×1) reconciling while F-NORTH and F-COAST broke, and the same
for tiers. All six groups reconcile at 100%.

Three worked spot checks were also run by hand:

- **Arithmetic**: line `H5-L00003-01`, base 19,775 × 0.95 (F-COAST) = 18,786.25 → half-up
  18,786 → × 1 (SILVER) = 18,786, equal to the billed unit price.
- **Rounding convention is material**: step-wise rounding differs from rounding once at the
  end on 280 of the first 4,000 lines (e.g. 156,675 × 1.1 × 0.92 → 158,556 step-wise vs
  158,555 round-once). Clause 3.2 requires step-wise, which is what the engine produces;
  getting this wrong would have put ~7% of lines a cent out and falsely flagged hundreds of
  clean invoices.
- **New diagnostic is a true positive**: line `H5-L00091-10` bills 145,744, exactly the
  rate F-COAST's ×0.92 would produce, while the invoice records F-NORTH (correct rate
  190,100) — a precisely identified wrong-facility billing rather than a generic price
  mismatch.

## Outcome

`notebooks_py/hospital_5/submission.csv` holds 1,050 rows; the combined repo-root
`submission.csv` now carries 2,798 rows across three hospitals (913 + 835 + 1,050).
Scored coverage is now hospitals 4 and 5; hospitals 2 and 3 remain unattempted. The
decision log is the trailing comment block of `07_aggregation_output.py`, and records the
premium/uplift ordering ambiguity within clause 3.1(d) — the contract states no order
between a Section 5 premium and a Section 6 uplift, the two are applied in that order
following Hospital 1's convention, and the alternative reading would differ only by
rounding and only on lines where both fire.
