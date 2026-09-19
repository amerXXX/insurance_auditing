# Master prompt — distilled audit method

<!--
This file is NOT a captured user request like the other files in this directory
(see README.md: "no prompt in this directory is invented"). It is a synthesized
specification, written after the fact, that consolidates the method actually
implemented in mainHP_1_final.ipynb and mainHP_4.ipynb into one instruction. Its
purpose: hand this to a fresh assistant, together with a hospital's contract and
invoice data, and it should reproduce the same audit method without re-deriving
it from scratch. It replaces no individual prompt record — those remain the
honest history of how the method was actually built.
-->

## Task

Meridian Health Assurance Group reimburses several hospitals under separately
negotiated contracts. For a given hospital, decide for each invoice whether it
is erroneous, and if so what it should have totalled. Output one row per
`invoice_id` in this exact schema:

```
invoice_id, flagged, error_category, expected_total_cents, billed_total_cents, confidence
```

All money is an integer number of cents. `flagged` is 0/1. `error_category` is
`|`-joined internal category names, or empty if not flagged. `confidence` is a
**deterministic audit-policy score**, not a statistical probability — see below.

## Ground rules (binding, not suggestions)

1. **Flag, don't guess.** An ambiguous or unrecognised billing description is
   marked for review, at low confidence. It is never silently treated as
   correct, and never silently invented a service identity either.
2. **Don't force predictions to match every label.** On a labelled hospital,
   the goal is calibrated honesty (high precision, disclosed recall gaps), not
   fitting the label file. A known, accepted recall cost is reported in the
   decision log, not engineered away.
3. **A confidently wrong extraction is worse than a flagged uncertainty.** When
   a contract basis cannot be established for a line (unmatched service,
   malformed date), carry the **billed** amount through as a provisional
   expected total rather than dropping or inventing a figure, and lower
   confidence accordingly.
4. **Re-extract each contract from its own clause headers.** Never assume a
   new hospital's contract sections line up positionally with a previous
   hospital's. Parse by heading text, then assert the extracted row counts
   against a manual read of the contract before trusting them downstream.

## Method, in execution order

### 1. Contract extraction

Parse the contract markdown by scanning for `## N. Section Title` headers and
pulling out the markdown tables under each into DataFrames (service, unit,
rate; thresholds; caps; bundles; discounts; exclusion windows; uplifts).
`assert len(extracted) == <manually counted rows>` for every table — this is
the single most effective bug-catcher in the whole pipeline, since a silent
off-by-one in table parsing propagates into every downstream price.

### 2. Service matching (billing description → contract service)

Billing `description` is free text, heavily abbreviated, and not a code. The
matcher must be conservative because a wrong service mapping contaminates
every downstream check.

- Normalize: strip trailing reference codes (`/AB-123`), split on `-`/`/`,
  lowercase, expand a fixed abbreviation table (`adv`→`advanced`, `spcm`→
  `specimen`, clinical-specialty abbreviations like `card`→`cardiac`, etc.).
- Score each candidate service by token-level exact / prefix / subsequence /
  fuzzy (`difflib`) evidence, apportioned so each description token and each
  service-name word can only be used once.
- Apply two structural vetoes before accepting a match: a clinical-specialty
  anchor in the description must not conflict with the candidate's, and a
  service-class anchor (`specimen/analysis`, `dialysis`, `wound care`,
  `consultation`, `transport`, `occupancy`, ...) must not conflict either.
- Three outcomes, not two:
  - `matched` — clear top candidate, clear margin over runner-up
    (`score >= MIN_SCORE`, `gap >= GAP_THRESHOLD`; `0.55` / `0.08` in this
    repo). Priced, not flagged.
  - `resolved_by_price` — text is tied, but the billed price is consistent
    with exactly one structurally-compatible candidate's plausible contract
    prices (base / premium / discount derived). Priced, not flagged. Billed
    price is **secondary evidence only**, never the primary basis for a match.
  - `needs_review` — neither. Not priced automatically, not auto-flagged as
    an error, listed for a human. The unrecognised description may still be a
    valid contracted service.
- Known limitation to carry forward: `plausible_unit_prices()` does not
  include bundle-substituted rates, so a bundle-linked ambiguous description
  can have strong secondary price evidence the matcher doesn't use. Leave it
  `needs_review` rather than special-case it; record the gap in the decision
  log.

### 3. Reused invoice IDs → occurrence mapping

Some invoice IDs are reused across two genuinely different transactions. The
line-ID's own group prefix (not the invoice ID) identifies the true
transaction group. Map line-item groups to invoice-table rows **chronologically**
(by `invoice_date`, then table row order) rather than by ID alone, via an
`occurrence_rank` computed independently on both sides and joined on
`(invoice_id, occurrence_rank)`. When collapsing to one row per invoice ID for
the final output, report the **later** occurrence — this is a convention
validated against Hospital 1's labels, then carried forward unchanged.

### 4. Contract checks (the equivalent of "Section 11" in both contracts)

Computed as boolean columns on `line_items` / `invoices`, independent of
pricing:

- contract-number mismatch; duplicate invoice IDs
- malformed / out-of-term / service-date-after-invoice-date service dates
- billed unit basis vs. the contract's stated unit for the matched service
- daily/per-patient quantity caps — applied **cumulatively** across all lines
  for the same patient + service + service-day, in line-ID order, not
  per-line
- same service billed twice for the same patient + service-day, "whether on
  one invoice or across several" — the **later** occurrence (by invoice date,
  then line ID) is the non-billable duplicate
- exclusion windows: `service_a` is the one that becomes non-billable when it
  falls within N days of `service_b`, regardless of which was billed later
- line arithmetic (`line_total == unit_price × quantity`) and invoice
  arithmetic (`invoice_total == sum(line_total)`), checked independently of
  contract pricing

Ambiguity note to log explicitly when a clause could be read two ways (e.g.
whether a duplicate-billing clause applies only to services with a numeric
cap, or to every service): state the reading taken and what the alternative
would change.

### 5. Pricing engine

Apply in the contract's own stated order — in both contracts here that order
is **bundle → facility → plan → premium/uplift → cumulative discount**, with
half-up-cent rounding applied after every stage, not once at the end.
Facility/plan multipliers are 1× when the contract states a single facility
and tier-blind pricing; keep the pricing step in the code anyway so the engine
shape is identical across hospitals even when a stage structurally never
fires (document that explicitly, don't delete the stage).

- Bundle: same-day, same-patient presence of the paired service substitutes a
  bundled rate for one or both legs.
- Threshold premiums: apply once an aggregate per-patient-per-service-day
  quantity exceeds a stated threshold — to the **full** day's quantity, not
  just the excess.
- Cumulative discounts: hospital-wide, counted across the whole contract
  term in service-date-then-line-ID order; the discount applies strictly
  *after* the line on which the threshold is crossed, not on that line
  itself.
- An unmatched service or malformed date: carry the billed line total through
  as the provisional expected amount (ground rule 3), never zero or omit it.
- Excluded (`exclusion_violation`) and non-billable-duplicate lines: expected
  total is exactly 0, not provisional.

### 6. Aggregation and confidence policy

Aggregate at invoice-*occurrence* level first (so a reused ID's two
transactions price independently), then collapse to one row per invoice ID
per step 3. Confidence is deterministic, applied as a sequence of caps, not a
weighted score:

- default `0.95` (nothing flagged) or `0.90` (something flagged)
- unknown/unmatched service present → cap `0.35`
- duplicate invoice ID, or any provisional expected total → cap `0.55`
- a "corrective-rate" category present (unit price / premium / discount /
  uplift mismatch) → cap `0.80`
- two or more distinct error categories → cap `0.75`
- take the minimum of every rule that applies

### 7. Evaluation (only where ground-truth labels exist)

Report, don't just compute: TP/FP/FN/TN, accuracy, precision, recall, F1;
per-category recall/precision against the label vocabulary (map internal
category names to the label vocabulary where they diverge, e.g.
`weekend_uplift_omitted` → `premium_omitted`); exact-match rate on
`expected_total_cents` split by labelled-correct vs. labelled-erroneous;
systematic residuals grouped by **failure type** (daily-cap correction,
duplicate-occurrence selection, exclusion-window handling, unknown-service
provisional pricing, ...), not a list of individual misses; and a confidence
calibration table, framed as a descriptive diagnostic on a small dev set, not
a statistical calibration claim. Labels are used to build and calibrate the
method once; they are never read by the runtime detector, and a labelled
hospital's predictions file is a development artifact, not a scored
submission.

### 8. Output

One row per invoice ID in the schema above. Before writing: assert the exact
column list, `invoice_id` uniqueness, `flagged ∈ {0,1}`, `confidence ∈ [0,1]`,
and (where every invoice must appear) row count equals the invoice table's
distinct ID count.

## Applying this to a new hospital

1. Read the new contract in full; do not assume its section numbering or
   clause order matches a previous hospital's — re-extract from headers.
2. Reuse the service-matching functions, alias tables, and thresholds
   verbatim unless the billing-description style is demonstrably different
   (same synthetic generator across hospitals in this exercise ⇒ it isn't).
3. Reuse the pricing-engine *shape* and the confidence-policy thresholds
   verbatim; only the contract-derived rate/threshold/discount **tables**
   change.
4. Re-derive the checks section against the new contract's actual clauses —
   do not assume Section 11 (or its equivalent) has the same sub-clauses.
5. If the new hospital has no labels, skip step 7; state that explicitly
   rather than fabricating a score, and note that confidence is carried over
   from whichever hospital's labels calibrated the method.
6. Write a decision log: contract-structure mapping to the calibration
   hospital, any clause read two ways and which reading was taken, and any
   known limitation carried over unchanged (cite it, don't re-discover it).

## Where the full detail lives

This file is a distillation. The actual iteration history — what was asked,
what changed, what broke, what was measured — is in the individual
`*.v1.md` / `*.v2.md` files in this directory, and the full decision logs are
the trailing comment block of `notebooks_py/hospital_1/09_output.py` and
`notebooks_py/hospital_4/07_aggregation_output.py` (the pipeline's last step
for each hospital).
