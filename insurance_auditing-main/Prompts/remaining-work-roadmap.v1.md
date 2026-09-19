# 09 — Remaining-work roadmap and ground rules (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1, full rebuild

## User request

> i am not confident with the what appraoch you use to extract servece matching on same note

Supplied a seven-step ordered roadmap (Section 10 → service matching → Section 11
checks → pricing in contract order → aggregation → label comparison → submission
file), plus two explicit ground rules:

> Do not mark unmatched descriptions as errors automatically. They should be marked
> for review because the billing description may correspond to a valid contracted service.

> Also, do not force the predictions to match every label. The goal is reliable
> precision and honest uncertainty, not confident guesses.

Also noted: a prior `NameError` came from running a Section 11.4 check before
`service_matches` existed, so service matching must come first.

## What changed

Full rebuild of cells 11+ in the supplied order. The two ground rules were treated
as binding constraints, not suggestions — see `11-service-matching.v2.md` for the
resulting behavioural change.

## Outcome

Replaced the earlier approach. The roadmap itself was added to the notebook as a
markdown cell so the ordering rationale travels with the code.
