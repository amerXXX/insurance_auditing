# Hospital 1 pipeline, part 2/9 — depends on 01_setup.py having run first
# (uses REPO_ROOT).

# Section 4 — extract Hospital 1 base rates

contract_path = REPO_ROOT / "contracts" / "hospital_1" / "provider_services_agreement.md"
contract_lines = contract_path.read_text(encoding="utf-8").splitlines()

rate_rows = []
inside_section_4 = False

for line_number, line in enumerate(contract_lines, start=1):

    if line.startswith("## 4. Rate Schedule"):
        inside_section_4 = True
        continue

    if inside_section_4 and line.startswith("## 5."):
        break

    if not inside_section_4 or not line.startswith("|"):
        continue

    values = [
        value.strip()
        for value in line.strip("|").split("|")
    ]

    # Skip the table header and separator row
    if values[0] in {"Service", "---"}:
        continue

    if len(values) != 4 or not values[2].startswith("GBP"):
        continue

    service = values[0]
    contract_unit = values[1]
    rate_text = values[2].replace("GBP", "").replace(",", "").strip()
    cap_text = values[3]

    # Convert GBP to integer cents exactly
    base_rate_cents = int(
        Decimal(rate_text) * 100
    )

    # Convert daily cap to an integer where one exists
    daily_cap = (
        int(re.search(r"\d+", cap_text).group())
        if re.search(r"\d+", cap_text)
        else pd.NA
    )

    rate_rows.append({
        "service": service,
        "contract_unit": contract_unit,
        "base_rate_cents": base_rate_cents,
        "daily_cap": daily_cap,
        "contract_section": "4",
        "source_line": line_number
    })

rate_schedule = pd.DataFrame(rate_rows)

# Basic validation
assert not rate_schedule.empty
assert rate_schedule["service"].is_unique
assert rate_schedule["base_rate_cents"].gt(0).all()


# Sections 5 and 6 — extract premiums and weekend uplifts

contract_text = contract_path.read_text(encoding="utf-8")
contract_lines = contract_text.splitlines()

threshold_rows = []
weekend_rows = []
section = None

for line_number, line in enumerate(contract_lines, start=1):

    if line.startswith("## 5. Threshold Premiums"):
        section = 5
        continue

    if line.startswith("## 6. Non-Business-Day Uplifts"):
        section = 6
        continue

    if line.startswith("## 7."):
        section = None

    if not line.startswith("|") or section is None:
        continue

    values = [
        value.strip()
        for value in line.strip("|").split("|")
    ]

    # Section 5
    if section == 5 and len(values) == 3:
        if values[0] in {"Service", "---"}:
            continue

        threshold_match = re.search(r"\d+", values[1])
        uplift_match = re.search(r"\d+", values[2])

        if threshold_match and uplift_match:
            threshold_rows.append({
                "service": values[0],
                "threshold_units": int(threshold_match.group()),
                "premium_percent": int(uplift_match.group()),
                "contract_section": "5",
                "source_line": line_number
            })

    # Section 6
    if section == 6 and len(values) == 2:
        if values[0] in {"Service", "---"}:
            continue

        uplift_match = re.search(r"\d+", values[1])

        if uplift_match:
            weekend_rows.append({
                "service": values[0],
                "weekend_uplift_percent": int(uplift_match.group()),
                "contract_section": "6",
                "source_line": line_number
            })

threshold_premiums = pd.DataFrame(threshold_rows)
weekend_uplifts = pd.DataFrame(weekend_rows)

assert len(threshold_premiums) == 9
assert len(weekend_uplifts) == 7


# Sections 7–9 — extract discounts, caps and bundles

contract_lines = contract_path.read_text(
    encoding="utf-8"
).splitlines()

discount_rows = []
cap_rows = []
bundle_rows = []
section = None

for line_number, line in enumerate(contract_lines, start=1):

    if line.startswith("## 7. Cumulative Volume Discounts"):
        section = 7
        continue

    if line.startswith("## 8. Daily Quantity Caps"):
        section = 8
        continue

    if line.startswith("## 9. Bundled Services"):
        section = 9
        continue

    if line.startswith("## 10."):
        section = None

    if not line.startswith("|") or section is None:
        continue

    values = [
        value.strip()
        for value in line.strip("|").split("|")
    ]

    # Section 7 — cumulative discounts
    if section == 7 and len(values) == 3:
        if values[0] in {"Service", "---"}:
            continue

        threshold = re.search(r"\d+", values[1])
        discount = re.search(r"\d+", values[2])

        if threshold and discount:
            discount_rows.append({
                "service": values[0],
                "threshold_units": int(threshold.group()),
                "discount_percent": int(discount.group()),
                "contract_section": "7",
                "source_line": line_number
            })

    # Section 8 — daily quantity caps
    elif section == 8 and len(values) == 2:
        if values[0] in {"Service", "---"}:
            continue

        cap = re.search(r"\d+", values[1])

        if cap:
            cap_rows.append({
                "service": values[0],
                "maximum_units_per_patient_day": int(cap.group()),
                "contract_section": "8",
                "source_line": line_number
            })

    # Section 9 — bundled rates
    elif section == 9 and len(values) == 4:
        if values[0] in {"Service A", "---"}:
            continue

        rate_a = int(
            Decimal(
                values[2].replace("GBP", "").replace(",", "").strip()
            ) * 100
        )

        rate_b = int(
            Decimal(
                values[3].replace("GBP", "").replace(",", "").strip()
            ) * 100
        )

        bundle_rows.append({
            "service_a": values[0],
            "service_b": values[1],
            "bundled_rate_a_cents": rate_a,
            "bundled_rate_b_cents": rate_b,
            "contract_section": "9",
            "source_line": line_number
        })

volume_discounts = pd.DataFrame(discount_rows)
daily_caps = pd.DataFrame(cap_rows)
bundles = pd.DataFrame(bundle_rows)

# Basic validation against the agreement
assert len(volume_discounts) == 11
assert len(daily_caps) == 7
assert len(bundles) == 3


# Section 10 — extract exclusion windows

contract_lines = contract_path.read_text(encoding="utf-8").splitlines()

exclusion_rows = []
section = None

for line_number, line in enumerate(contract_lines, start=1):

    if line.startswith("## 10. Exclusion Windows"):
        section = 10
        continue

    if line.startswith("## 11."):
        section = None

    if not line.startswith("|") or section is None:
        continue

    values = [
        value.strip()
        for value in line.strip("|").split("|")
    ]

    if section == 10 and len(values) == 3:
        if values[0] in {"Service", "---"}:
            continue

        days_match = re.search(r"\d+", values[1])
        if days_match:
            exclusion_rows.append({
                "service_a": values[0],
                "window_days": int(days_match.group()),
                "service_b": values[2],
                "contract_section": "10",
                "source_line": line_number
            })

exclusion_windows = pd.DataFrame(exclusion_rows)

assert len(exclusion_windows) == 6
