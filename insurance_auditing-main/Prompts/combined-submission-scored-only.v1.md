# Combined submission.csv: scored hospitals only (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Post-Hospital-5, prompted by an external grading dashboard result

## User request

The candidate shared a screenshot of an automated grading dashboard (names of other
candidates masked) showing their own row: Initial submission F1 0.322, but the
Reproduction run (the candidate's committed code, re-executed by the grader on the same
invoices) carried a flag reading "913 of their invoices missing." Asked:

> i am number 26 can yo usee the results

Followed by, after being asked whether the dashboard grades the pushed GitHub repo
directly, and whether to act on the hypothesis that this was Hospital 1's row count
leaking into the scored file:

> Yes, it pulls from my GitHub repo [and] Yes, fix it now

The candidate then shared the dashboard's own legend, clarifying that Reproduction
re-executes the submitted commit's code from scratch (not just re-reading the committed
CSV) and that the grader's invoice set includes deliberately-planted "decoy" invoices not
present in this repository's local data.

## What changed

`insurance_auditing-main/submission.csv` is for hospitals 2/3/4/5 per the exercise brief;
Hospital 1 (the labelled development set) was never meant to be part of the scored file.
An earlier session combined every hospital's output into one file regardless, at the
candidate's own explicit request at the time ("combine hospital_1_dev_predictions +
submission" and later "each hospital has to have its submission.csv... combine the
results"). 913 -- the exact row count of Hospital 1's output -- appearing as a "missing
invoices" flag on the Reproduction run was the signal that this scope mismatch had made
it into the graded file.

`notebooks_py/main.py` now distinguishes scored from dev-only hospitals structurally
rather than by name: a hospital is scored unless
`insurance_auditing-main/labels/<hospital_N>_labels.csv` exists. Every hospital still
writes its own `hospital_N/submission.csv` unconditionally (Hospital 1's dev/calibration
output is unaffected and still produced); only the *combined* repo-root `submission.csv`
now excludes dev-only hospitals. This generalises correctly if hospital_2 or hospital_3
are added later -- neither has a labels file either, per the exercise brief, so both would
be included in the combined file without any code change.

## Caveat, stated honestly

The dashboard's own legend indicates its invoice set includes decoy invoices not present
in this repository's local `invoices/` data, so "913 missing" may not refer precisely to
Hospital 1's local row count -- the match could be coincidental. The fix was made and is
correct regardless: it corrects a real, independently-identifiable scope error against the
exercise's own stated deliverable (`submission.csv` in the schema of
`submission_template.csv`, for hospitals 2/3/4/5), whether or not it is the exact
explanation for that specific dashboard flag.

## Outcome

Re-ran `notebooks_py/main.py`. The combined `submission.csv` is now 1,885 rows (835 from
hospital 4 + 1,050 from hospital 5), containing no `INV-H1-*` rows -- verified directly.
`notebooks_py/hospital_1/submission.csv` (913 rows) is unaffected and still written.
