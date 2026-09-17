# 1 — Hospital 1, initial EDA (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1

## User request

> listen; i want to start this project where i need to finish hospital 1 first so i want to start simply by visuallise the data (in a manner that helps understands the task and what we have ok? i am going to work in main..ipynb as the solotion for HP1 then latter i will ask you about other hospitlas in the same way but not now in this session.
> so help me in creating the work simply and avoid compexity

## What was built

First version of `main.ipynb`, scoped to Hospital 1 only, purely descriptive — no error-detection logic. Loaded `invoices/hospital_1_invoices.csv`, `hospital_1_line_items.csv`, `hospital_1_labels.csv` and charted:

- label distribution (913 labelled rows, 6.4% erroneous)
- error-category breakdown (18 categories, no single one dominant)
- invoice totals, plan-tier counts, line-items-per-invoice
- the free-text description problem (488 distinct descriptions vs. a rough count of contracted services)
- a first pass at date sanity (service_date vs. invoice_date)

## Status at time of writing

Notebook executed end-to-end, no errors, 6 charts rendered. 28 cells (17 code, 11 markdown).

## Caveat carried forward

Contracted-service count was estimated by eye at "110" from a first read of Section 4 — later corrected to the true figure (108) once Section 4 was parsed programmatically (see record 5).
