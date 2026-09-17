# 11 — Service matching (v2)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1, step 2 of roadmap — **supersedes v1**

## Change from v1

Driven by the two ground rules in prompt 09. Three outcomes replace v1's two:

| Status | Meaning | Priced? | Flagged? |
| --- | --- | --- | --- |
| `matched` | clear top candidate, clear margin over runner-up | yes | no |
| `resolved_by_price` | text tie, but billed price consistent with exactly one candidate | yes | no |
| `needs_review` | neither — **not** assumed to be an error | no | **no** |

`needs_review` descriptions are excluded from automatic pricing and listed
separately for a human. They are **not** auto-flagged, because a description the
matcher does not recognise may still be a valid contracted service.

## Result

488 unique descriptions: 463 `matched`, 16 `resolved_by_price`, 9 `needs_review`.

## Accepted cost

The 9 `needs_review` descriptions sit on 5 invoices that the labels mark erroneous.
Leaving them unflagged costs recall (0.914 instead of ~1.0). This was accepted
deliberately rather than fitted away — honest uncertainty over a confident guess.
