# 6 — Where the Section 2 definitions are actually used (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1

## User request

> wherre these applied 2. Interpretation
> 2.1 "Service Day" means the calendar day recorded as the Service Date of the line item.
> 2.2 "Business Day" means any Service Day other than a Saturday or a Sunday.
> 2.3 "Unit" means one billable unit of the Service on the unit basis stated for that Service in Section 4.
> 2.4 "Cumulative utilisation" means the running total of Units of a Service billed under this Agreement, counted in Service Date order, up to but excluding the line item being priced.

## What was checked

Searched the contract text for every use of each defined term outside its own definition in §2.

## Key finding

Each term feeds a different aggregation scope:

- **2.1 Service Day** → §5 (threshold premiums) and §8 (daily caps), both scoped per Patient per Service Day
- **2.2 Business Day** → §6 (weekend/holiday uplift) only
- **2.3 Unit** → the thing `quantity` counts, defined per-service in §4's `Unit basis` column; not comparable across services
- **2.4 Cumulative utilisation** → §7 only, and deliberately different scope from 2.1: counted across the *whole contract term*, aggregated across *all patients*, not per-patient-per-day

## Status

No notebook change — this was groundwork for the §5/§7/§8 grouping logic built in later records.
