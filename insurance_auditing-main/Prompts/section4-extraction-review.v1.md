# 8 — Reviewing the user's Section 4 rate-schedule extraction (v1)

<!-- Prompt record. Wording preserved as supplied, including spelling. Records actual changes made; does not invent timing or results. -->

**Assistant used:** Claude
**Phase:** Hospital 1

## User request

> ```python
> # Section 4 — extract Hospital 1 base rates
>
> from pathlib import Path
> from decimal import Decimal
> import re
> import pandas as pd
> from IPython.display import display
>
> contract_path = REPO_ROOT/ "contracts" / "hospital_1" / "provider_services_agreement.md"
> contract_lines = contract_path.read_text(encoding="utf-8").splitlines()
>
> rate_rows = []
> inside_section_4 = False
>
> for line_number, line in enumerate(contract_lines, start=1):
>
>     if line.startswith("## 4. Rate Schedule"):
>         inside_section_4 = True
>         continue
>
>     if inside_section_4 and line.startswith("## 5."):
>         break
>
>     if not inside_section_4 or not line.startswith("|"):
>         continue
>
>     values = [
>         value.strip()
>         for value in line.strip("|").split("|")
>     ]
>
>     # Skip the table header and separator row
>     if values[0] in {"Service", "---"}:
>         continue
>
>     if len(values) != 4 or not values[2].startswith("GBP"):
>         continue
>
>     service = values[0]
>     contract_unit = values[1]
>     rate_text = values[2].replace("GBP", "").replace(",", "").strip()
>     cap_text = values[3]
>
>     # Convert GBP to integer cents exactly
>     base_rate_cents = int(
>         Decimal(rate_text) * 100
>     )
>
>     # Convert daily cap to an integer where one exists
>     daily_cap = (
>         int(re.search(r"\d+", cap_text).group())
>         if re.search(r"\d+", cap_text)
>         else pd.NA
>     )
>
>     rate_rows.append({
>         "service": service,
>         "contract_unit": contract_unit,
>         "base_rate_cents": base_rate_cents,
>         "daily_cap": daily_cap,
>         "contract_section": "4",
>         "source_line": line_number
>     })
>
> rate_schedule = pd.DataFrame(rate_rows)
>
> # Basic validation
> assert not rate_schedule.empty
> assert rate_schedule["service"].is_unique
> assert rate_schedule["base_rate_cents"].gt(0).all()
>
> print("Contract services extracted:", len(rate_schedule))
> print("Services with daily caps:",
>       rate_schedule["daily_cap"].notna().sum())
>
> display(rate_schedule.head(10))
> ```

## What was checked

Ran the supplied code against the real contract file and cross-checked the output.

## Key findings

- Runs clean: 108 services extracted, 7 with daily caps, all three assertions pass.
- No rate string in Section 4 has more than 2 decimal places, so `int(Decimal(rate_text) * 100)` never silently truncates here — flagged as something to watch if this exact pattern is reused elsewhere.
- `daily_cap` column ends up `dtype: object` (mixing `int` and `pd.NA`) rather than a nullable integer — suggested `.astype("Int64")` for cleaner downstream comparisons.
- New finding: the contract's `contract_unit` wording ("per day of service", "per item supplied", etc.) is a different vocabulary from the billed `unit_basis_as_billed` values ("per_day", "per_item", etc.). They map 1-to-1 but aren't equal as strings — a normalization step is needed before `wrong_unit_basis` (11 labelled cases) can be checked.

## Status

Review of the user's own code — no notebook change made by the assistant.
