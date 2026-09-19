# Invoice Audit Exercise

Meridian Health Assurance Group reimburses five hospitals under five separately
negotiated service contracts. Each hospital submits invoices for the patients
it has treated. Some of those invoices are wrong — a rate that does not match
the contract, an adjustment applied when it was not due or omitted when it was,
a quantity beyond a contractual limit, a service billed twice.

Your job is to find the wrong ones.

## How to run (reproduce `submission.csv`)

This repository is runnable end-to-end from a fresh clone. The pipeline lives as
plain Python files under `notebooks_py/`, a sibling folder of this one — there is
no `.ipynb` in this repository.

### 1. Set up the environment

```bash
git clone <this-repo-url>
cd <repo-root>                   # the folder containing both insurance_auditing-main/ and notebooks_py/
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r insurance_auditing-main/requirements.txt
```

Dependencies are pinned in [`requirements.txt`](requirements.txt) (just `pandas`).
Requires Python 3.10+.

### 2. Run the pipeline

```bash
python notebooks_py/main.py
```

This runs every hospital's pipeline in turn and combines their outputs. Each
`notebooks_py/hospital_N/` folder holds a numbered sequence of plain Python
files (`01_setup.py` through the last step), meant to be read and executed top
to bottom — like notebook cells split into files for readability. Each step
depends on variables the previous ones defined, so run (or read) them in order.

- **`hospital_1/`** audits hospital 1, the labelled development set, and
  evaluates against `labels/hospital_1_labels.csv` — accuracy, precision,
  recall, F1, per-category performance, residual analysis, and confidence
  calibration, printed to the console by its evaluation step. Hospital 1 is
  not scored.
- **`hospital_4/`** audits hospital 4 — the scored contribution.

Each hospital writes its own `hospital_N/submission.csv`; `main.py` then
combines every `hospital_*/submission.csv` it finds into one file at the repo
root: **`submission.csv`**, in the exact column format of
`submission_template.csv` (`invoice_id, flagged, error_category,
expected_total_cents, billed_total_cents, confidence`).

To add a new hospital once its data/contract exist (e.g. hospital 5): create
`notebooks_py/hospital_5/` with the same numbered-file pattern, ending in a
step that writes `hospital_5/submission.csv`. `main.py` discovers
`hospital_*` folders automatically — it needs no changes.

### 3. Output

- `submission.csv` (repo root) — the combined submission across every
  hospital `main.py` ran.
- `notebooks_py/hospital_1/submission.csv` — hospital 1's own predictions
  (development/calibration only, not scored).
- `notebooks_py/hospital_4/submission.csv` — hospital 4's own predictions
  (the scored contribution to the combined file).

### Scope

Given the stated six-to-eight hour time budget and that full coverage of all
five hospitals is not expected, this submission covers hospital 1
(development/calibration) and hospital 4 (scored). Hospitals 2, 3, and 5 were
not attempted. See `../one_page_Logs.pdf` for the decision log and
`../Error_Analysis_HP1.pdf` for the hospital-1 error analysis.

## What you have

```
contracts/hospital_1/ ... contracts/hospital_5/
    The five contracts, as Markdown and as plain text. Each hospital's
    contract is presented differently; one of them is split across several
    documents. Read whichever format suits your tooling.

invoices/hospital_N_invoices.csv
    One row per invoice: invoice_id, hospital_id, contract_number,
    invoice_date, patient_id, facility_code, plan_tier, admission_date,
    discharge_date, invoice_total_cents.

invoices/hospital_N_line_items.csv
    One row per line item: line_id, invoice_id, line_no, service_date,
    description, quantity, unit_basis_as_billed, unit_price_cents,
    line_total_cents.

invoices/hospital_N_invoices.jsonl
    The same data, one JSON object per invoice, with the line items nested.
    Use whichever shape you prefer; they carry identical information.

labels/hospital_1_labels.csv
    Ground truth for hospital 1 only — your development set.

submission_template.csv
    The format your predictions must take.
```

All money is an integer number of cents. There are no floating-point amounts
anywhere in the data, and there should be none in your answer.

The line-item `description` is the hospital's own free-text billing
description. It is not a contract term, it is not a code, and the same
contracted service is described many different ways across the data.
Establishing which contracted service a description refers to is part of the
task.

## The task

For hospitals hospital_2, hospital_3, hospital_4, hospital_5, decide for each invoice whether it is erroneous, and
submit your predictions in the format of `submission_template.csv`:

| column | meaning |
|---|---|
| `invoice_id` | the invoice you are making a claim about |
| `flagged` | `1` if you believe the invoice is erroneous, `0` otherwise |
| `error_category` | your own short label for what is wrong; free text |
| `expected_total_cents` | what you believe the invoice *should* have totalled |
| `billed_total_cents` | what it actually totalled |
| `confidence` | your confidence in the row, between 0 and 1 |

Submit a row for every invoice you have an opinion about. Rows for invoices you
believe are correct are useful and are scored.

Hospital 1 is labelled. Use it to develop and to calibrate; it is not scored.

## How this is assessed

**Complete coverage of all five contracts is not expected.** The exercise is
deliberately larger than the time budget. Sequencing — deciding what to attempt
first and what to leave — and reporting honestly on what you did not attempt
are explicitly part of what is being evaluated. A submission covering two
hospitals well, with a clear account of why those two and what would come next,
is a stronger result than a thin pass over all four.

**A confidently wrong extraction is worse than a flagged uncertainty.** If you
tell us a rate is 42.00 and it is not, that error propagates silently into
every invoice touching that service. If you tell us you are unsure, a human
reviews it and the cost is a few minutes. Scoring reflects this: your stated
`confidence` is used, and calibration is measured. Say what you do not know.

## Time budget

Six to eight hours, spread over one week. That is a **cap**, not a target. Do
not exceed it. If you find yourself at the cap with work outstanding, stop and
write down what you would have done next — that write-up is worth more to us
than the extra hours.

## AI assistance

Using AI assistance is permitted and expected. It must be disclosed. Include
your prompts as versioned files in the repository (see deliverables) so we can
see how you worked, not just what you produced.

## Deliverables

1. **A runnable repository.** We should be able to clone it, follow your README,
   and reproduce your submission file. Pin your dependencies.
2. **`submission.csv`** in the template format.
3. **A short evaluation report** giving per-category performance on the
   hospital 1 development set, and an error analysis grouped by *failure type*
   — not a list of individual misses, but the three or four systematic ways
   your approach goes wrong, with an example of each.
4. **Your prompts, as versioned files** in the repository. If you iterated on a
   prompt, we would like to see that it was iterated on.
5. **A one-page decision log**: the assumptions you made, the ambiguities you
   found and could not resolve, and what you decided to do about each. If you
   read a clause two ways and had to pick one, that belongs here.

## Ground rules

- The data is synthetic. There are no real patients and no real hospitals.
- Everything you need is in this package. There is nothing to look up
  externally.
- If something in a contract seems genuinely ambiguous, it may well be. Record
  your reading and move on; do not spend the budget on it.
