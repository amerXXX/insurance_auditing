# 7 — Implementing Section 3's rounding and adjustment order (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1

## User request

> 3. Calculation Conventions
> 3.1 All monetary amounts are expressed in whole cents. Where the application of a multiplier, premium or discount produces a fraction of a cent, the result shall be rounded to the nearest whole cent, with exact halves rounded away from zero ("half up"). Rounding is applied after each individual step of the calculation, not once at the end.
> 3.2 Where more than one adjustment applies to the same Service, the adjustments shall be applied to the base rate strictly in the following order: (a) substitution of a bundled rate; (b) the facility multiplier; (c) the plan-tier multiplier; (d) any premium or uplift; and (e) any cumulative volume discount. The line total is then the resulting unit rate multiplied by the billed quantity.
> 3.3 The line total for a line item is the effective unit rate multiplied by the billed quantity. The invoice total is the sum of the line totals on that invoice.

## What was built

`round_half_up_cent()` (Decimal + ROUND_HALF_UP) and `price_line_item()`, implementing 3.2's fixed five-step order with rounding after every step per 3.1.

## Key findings

- Python's built-in `round()` uses banker's rounding, not half-up — `round(2050.5)` gives 2050, the contract requires 2051. Flagged as a landmine for any pricing code that uses the built-in.
- Checked whether any Hospital 1 service stacks more than one adjustment type: no overlap at all between §5, §6, §7 services or the §9 bundle-pair services. Step (d) never needs to compound two percentages for this hospital — noted as a fact about this contract, not a rule to assume elsewhere.
- (b) facility multiplier and (c) plan-tier multiplier are no-ops for Hospital 1 (clauses 1.2 and 1.3), but kept as generic parameters since other hospitals may not have the same exemptions.

## Status

Function written and unit-tested against §4/§5 directly (Ambulatory Ophthalmic Case Conference, 5 vs. 8 visits). Not yet validated against real billed line items — that needs Phase 3's service mapping first. Not yet added to `main.ipynb`.
