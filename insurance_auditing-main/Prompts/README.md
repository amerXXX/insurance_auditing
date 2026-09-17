# Prompt and iteration record

A per-task record of the prompts that drove this repository, in `taskName.vN.md` format.

Wording is preserved as supplied, including spelling. Each file records the actual
change made and, where relevant, the decision or assumption logged at that point.
No prompt in this directory is invented, and no timing or result is invented.

## Scope and honesty note

This is a record of **recorded** prompts, not a complete transcript. Two sources:

| Files | Phase | Assistant |
| --- | --- | --- |
| 01–06 | Hospital 1, initial rule checks | ChatGPT |
| 07–18 | Hospital 1 rebuild, verification, Hospital 2 | Claude |

Items still to be supplied by the candidate before submission are listed in
`18-prompt-record.v1.md`: actual work time per phase, any earlier prompts predating
the ChatGPT record, and calendar dates if required.

## Versioning

A `vN` suffix marks a task that genuinely went through more than one version.
Superseded versions are **kept**, with the reason for supersession stated, so the
reasoning is auditable rather than silently overwritten.

| Task | Versions | Why it changed |
| --- | --- | --- |
| `11-service-matching` | v1 → v2 | v1 auto-flagged unmatched descriptions as errors; v2 routes them to review instead |
| `15-notebook-assembly` | v1 → v2 | v1 predated the seven-step roadmap and the two ground rules |
| `16-execution-debug` | v1 → v2 | two distinct execution failures, each with its own cause |

## Index

| File | Task |
| --- | --- |
| `01-term-check-clause-1-1.v1.md` | Clause 1.1 contract-term date check |
| `02-imports-and-scope.v1.md` | Consolidate imports and loading into one cell |
| `03-datadir-path-fix.v1.md` | `FileNotFoundError` — underscore vs hyphen in path |
| `04-interpret-term-issues.v1.md` | Explain the 12 term issues; add reason column |
| `05-record-findings.v1.md` | Record findings before moving to the next rule |
| `06-term-only-calculation.v1.md` | Term-only partial total, explicitly not final |
| `07-project-orientation.v1.md` | Read repo, contract, labels, existing notebook |
| `08-status-stocktake.v1.md` | Stage/status table; fixed the work ordering |
| `09-remaining-work-roadmap.v1.md` | Seven-step roadmap + two binding ground rules |
| `10-exclusion-windows-section-10.v1.md` | Section 10 extraction (6 rules) |
| `11-service-matching.v1.md` | Description → contract service (superseded) |
| `11-service-matching.v2.md` | Three-outcome matching with review queue |
| `12-section-11-checks.v1.md` | Section 11 + daily caps + unit basis |
| `13-pricing-engine.v1.md` | Clause 3.2 pricing order; duplicate-join bug fix |
| `14-label-calibration.v1.md` | Dev-set comparison against Hospital 1 labels |
| `15-notebook-assembly.v1.md` | First assembly, 20 cells (superseded) |
| `15-notebook-assembly.v2.md` | Final assembly, 28 cells |
| `16-execution-debug.v1.md` | `NameError` — undefined `invoices_dedup` |
| `16-execution-debug.v2.md` | `KeyError` — stale snapshot taken before Step 3 |
| `17-hospital-2-prose-contract.v1.md` | Hospital 2: prose contract, structure rewrite |
| `18-prompt-record.v1.md` | This record |

## Validated results referenced in these files

Hospital 1 (labelled, not scored — used for calibration):

| Metric | Value |
| --- | --- |
| Precision | 1.000 (0 false positives) |
| Recall | 0.914 (53/58) |
| Exact expected-total match on labelled-correct invoices | 100% (855/855) |

All 5 false negatives are invoices whose only issue is an unmatched description,
left unflagged deliberately under the ground rule in `09-remaining-work-roadmap.v1.md`.

Hospital 2 (no labels available): 1072/1113 fully-matched invoices reconcile
exactly (96.3%). Confidence values are lower on principle, since the Hospital 1
reconciliation check cannot be repeated without labels.
