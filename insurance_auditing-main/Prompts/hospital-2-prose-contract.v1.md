# 17 — Hospital 2, prose contract (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 2

## User request

> can you creat mainhp2 following same strucre in prevoius noot ceaking section by
> section and then aggregate and complete the supmision

## Key finding — the structure does not transfer

Hospital 1's contract is **tables**. Hospital 2's is **prose**, and says so:

> _Executed as a deed. No tables are used in this instrument._
> 1.4 The rates for individual Services are not gathered into a single schedule.

Rates live inside numbered clauses, interleaved with boilerplate articles
(Notices, Audit Rights, Force Majeure). Every Hospital 1 extraction cell had to be
rewritten as clause-block parsing. Extracted: 76 services, 9 premiums,
8 weekend uplifts, 12 discount tiers, 8 daily caps, 6 bundle clauses, 6 exclusions.

## Contract differences logged

* **Compound unit.** Clause 4.2 reads "GBP 106.25 per hour, per item" — looks
  ambiguous, but `per_hour_per_item` occurs 163 times in the data, so it is a real
  compound unit, not a drafting error.
* **Bundles stated reciprocally.** Each clause restates the pair from its own side —
  6 clauses, **3** unique pairs. De-duplicated before use.
* **No duplicate-service-billing clause.** Hospital 2 has no equivalent of
  Hospital 1's 11.4. Flagging it would mean inventing a rule this contract does not contain.
* **New rule:** 13.1, invoices due within 60 days of discharge. Checked — zero violations
  (max observed lag 10 days).
* **Exclusion direction.** Hospital 2's wording makes service A the excluded one.
  Hospital 1's later-invoice convention came from *labels*; Hospital 2 has none,
  so the contract text is followed literally instead.

## Matcher change

Bundled rates added to the plausible-price set for tie-breaking — without them, a
line legitimately billed at its bundled rate looks impossible. Resolved 3 more
descriptions (15 → 12 `needs_review`).

## Status at time of writing

Extraction, matching, and pricing validated: **1072/1113** fully-matched invoices
reconcile exactly (96.3%). Mismatches confirmed as scattered seeded errors, not a
systematic bug — verified by tracing one bundle case line by line (both halves of
a bundle pair billed at standalone rates = genuine `bundle_not_applied`).
Notebook assembly and the combined submission were still outstanding.

## Caveat carried forward

Hospital 2 has **no label file**. Hospital 1's 100%-exact-reconciliation check is
not available here, so confidence values must be lower on principle.
