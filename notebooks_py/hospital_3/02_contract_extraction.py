# Hospital 3 pipeline, part 2/7 — depends on 01_setup.py having run first
# (uses REPO_ROOT).

## Contract structure: three documents, read together
#
# Base Agreement clause 1.3: "This Base Agreement is to be read together with Appendix B
# (Rate Schedule) and with any amendment executed under clause 1.4. In the event of
# conflict, an amendment prevails over Appendix B, and Appendix B prevails over this Base
# Agreement."
#
# | Document              | Carries                                                        |
# |-----------------------|----------------------------------------------------------------|
# | base_agreement.md     | rules: premiums (4), uplifts (5), discounts (6), caps (7),      |
# |                       | bundles (8), exclusion windows (9), invoicing (10)              |
# | appendix_b_...md      | B.1 the rate schedule as originally agreed, with a daily-cap    |
# |                       | column                                                          |
# | amendment_no_1.md     | A1.2 substituted rates, A1.3 additional services, both from     |
# |                       | 1 January 2025 and applied *by Service Date* (A1.1.2)           |
#
# The three are cross-checked against one another below rather than trusted individually,
# because clause 1.3 only tells you which wins in a conflict -- it does not tell you
# whether one exists. Two checks matter: the amendment's "Rate to 31 December 2024" column
# must restate Appendix B (otherwise the pre-2025 rate is genuinely disputed), and the
# Base Agreement's section 7 caps must agree with Appendix B's own daily-cap column.

CONTRACT_NUMBER = "INS-H3-2024-0562"
CONTRACT_START = pd.Timestamp("2024-01-01")       # base 1.2
CONTRACT_END = pd.Timestamp("2025-12-31")         # base 1.2
FACILITY_CODE = "F-MAIN"                          # base 1.5
AMENDMENT_EFFECTIVE = pd.Timestamp("2025-01-01")  # A1.1.1, applied by Service Date per A1.1.2

contracts_dir = REPO_ROOT / "contracts" / "hospital_3"
base_text = (contracts_dir / "base_agreement.md").read_text(encoding="utf-8")
appendix_text = (contracts_dir / "appendix_b_rate_schedule.md").read_text(encoding="utf-8")
amendment_text = (contracts_dir / "amendment_no_1.md").read_text(encoding="utf-8")


def table_rows(text, start_prefix, stop_prefix):
    """Markdown table rows between two headings, as stripped cell lists."""
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith(start_prefix):
            inside = True
            continue
        if inside and stop_prefix and line.startswith(stop_prefix):
            break
        if not inside or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] in ("Service", "Service A", "---") or set("".join(cells)) <= set("-: "):
            continue
        out.append(cells)
    return out


def gbp_to_cents(text):
    return int(Decimal(text.replace("GBP", "").replace(",", "").strip()) * 100)


def first_int(text):
    match = re.search(r"\d+", text or "")
    return int(match.group()) if match else None


# ---- Appendix B.1: the rate schedule as originally agreed ----
appendix_rows = table_rows(appendix_text, "## B.1 Rates", "## B.2")
rate_schedule = pd.DataFrame([{
    "service": service,
    "contract_unit": unit,
    "base_rate_cents": gbp_to_cents(rate),
    "daily_cap": first_int(cap) if first_int(cap) is not None else pd.NA,
    "source": "appendix_b",
} for service, unit, rate, cap in appendix_rows])
assert len(rate_schedule) == 118
assert rate_schedule["service"].is_unique

# ---- Amendment A1.2: substituted rates (by Service Date, from 1 January 2025) ----
substituted_rows = table_rows(amendment_text, "## A1.2 Substituted Rates", "## A1.3")
substituted_rates = pd.DataFrame([{
    "service": service,
    "contract_unit": unit,
    "rate_before_cents": gbp_to_cents(old),
    "rate_from_cents": gbp_to_cents(new),
} for service, unit, old, new in substituted_rows])
assert len(substituted_rates) == 7

# ---- Amendment A1.3: additional services, not contracted before the effective date ----
additional_rows = table_rows(amendment_text, "## A1.3 Additional Services", "## A1.4")
additional_services = pd.DataFrame([{
    "service": service,
    "contract_unit": unit,
    "base_rate_cents": gbp_to_cents(rate),
    "source": "amendment_a1_3",
} for service, unit, rate in additional_rows])
assert len(additional_services) == 2

# ---- Cross-check the three documents against one another ----
_appendix_rate = dict(zip(rate_schedule["service"], rate_schedule["base_rate_cents"]))
_appendix_unit = dict(zip(rate_schedule["service"], rate_schedule["contract_unit"]))
for row in substituted_rates.itertuples():
    assert row.service in _appendix_rate, (
        f"A1.2 substitutes a rate for {row.service!r}, which is not in Appendix B"
    )
    assert _appendix_rate[row.service] == row.rate_before_cents, (
        f"Conflict for {row.service!r}: Appendix B has {_appendix_rate[row.service]}, "
        f"A1.2's pre-2025 column has {row.rate_before_cents}"
    )
    assert _appendix_unit[row.service] == row.contract_unit, (
        f"Unit basis conflict for {row.service!r} between Appendix B and A1.2"
    )
for row in additional_services.itertuples():
    assert row.service not in _appendix_rate, (
        f"A1.3 adds {row.service!r} as a new Service, but Appendix B already contracts it"
    )

# The full contracted list is Appendix B plus the services the amendment adds. Additional
# services carry a contracted_from date; everything else is contracted for the whole term.
rate_schedule["contracted_from"] = CONTRACT_START
additional_services["contracted_from"] = AMENDMENT_EFFECTIVE
additional_services["daily_cap"] = pd.NA
rate_schedule = pd.concat([rate_schedule, additional_services], ignore_index=True)
assert len(rate_schedule) == 120

# ---- Base Agreement rules ----
premium_rows = table_rows(base_text, "## 4. Threshold Premiums", "## 5.")
threshold_premiums = pd.DataFrame([{
    "service": service, "threshold_units": first_int(threshold), "premium_percent": first_int(uplift),
} for service, threshold, uplift in premium_rows])
assert len(threshold_premiums) == 14

weekend_rows = table_rows(base_text, "## 5. Non-Business-Day Uplifts", "## 6.")
weekend_uplifts = pd.DataFrame([{
    "service": service, "weekend_uplift_percent": first_int(uplift),
} for service, uplift in weekend_rows])
assert len(weekend_uplifts) == 12

discount_rows = table_rows(base_text, "## 6. Cumulative Volume Discounts", "## 7.")
volume_discounts = pd.DataFrame([{
    "service": service, "threshold_units": first_int(threshold), "discount_percent": first_int(discount),
} for service, threshold, discount in discount_rows])
assert len(volume_discounts) == 19

cap_rows = table_rows(base_text, "## 7. Daily Quantity Caps", "## 8.")
daily_caps = pd.DataFrame([{
    "service": service, "maximum_units_per_patient_day": first_int(cap),
} for service, cap in cap_rows])
assert len(daily_caps) == 12

bundle_rows = table_rows(base_text, "## 8. Bundled Services", "## 9.")
bundles = pd.DataFrame([{
    "service_a": a, "service_b": b,
    "bundled_rate_a_cents": gbp_to_cents(rate_a), "bundled_rate_b_cents": gbp_to_cents(rate_b),
} for a, b, rate_a, rate_b in bundle_rows])
assert len(bundles) == 5

exclusion_rows = table_rows(base_text, "## 9. Exclusion Windows", "## 10.")
exclusion_windows = pd.DataFrame([{
    "service_a": a, "window_days": first_int(window), "service_b": b,
} for a, window, b in exclusion_rows])
assert len(exclusion_windows) == 10

# Appendix B prevails over the Base Agreement (clause 1.3), so a disagreement on the daily
# caps would be a real conflict to report rather than a parsing artefact. Assert they agree.
_appendix_caps = {
    row.service: int(row.daily_cap)
    for row in rate_schedule.itertuples() if pd.notna(row.daily_cap)
}
_base_caps = dict(zip(daily_caps["service"], daily_caps["maximum_units_per_patient_day"]))
assert _appendix_caps == _base_caps, (
    "Daily caps disagree between Appendix B's column and Base Agreement section 7: "
    f"{set(_appendix_caps.items()) ^ set(_base_caps.items())}"
)

# Every rule must name a Service that is actually contracted, or it could never fire.
_contracted = set(rate_schedule["service"])
for frame, column in [(threshold_premiums, "service"), (weekend_uplifts, "service"),
                      (volume_discounts, "service"), (daily_caps, "service"),
                      (bundles, "service_a"), (bundles, "service_b"),
                      (exclusion_windows, "service_a"), (exclusion_windows, "service_b")]:
    unknown = set(frame[column]) - _contracted
    assert not unknown, f"Rule names non-contracted service(s): {unknown}"

SUBSTITUTED_RATE_FROM = dict(zip(substituted_rates["service"], substituted_rates["rate_from_cents"]))
CONTRACTED_FROM = dict(zip(rate_schedule["service"], rate_schedule["contracted_from"]))
BASE_RATE = dict(zip(rate_schedule["service"], rate_schedule["base_rate_cents"]))


def base_rate_for(service, service_date):
    """Appendix B rate, or the amendment's substituted rate for Service Dates from 2025.

    A1.1.2: the Amendment applies by Service Date; the invoice's own date is irrelevant.
    Returns None where the Service was not contracted on that Service Date at all (A1.3).
    """
    if service is None or pd.isna(service) or pd.isna(service_date):
        return None
    if service_date < CONTRACTED_FROM.get(service, CONTRACT_START):
        return None
    if service_date >= AMENDMENT_EFFECTIVE and service in SUBSTITUTED_RATE_FROM:
        return SUBSTITUTED_RATE_FROM[service]
    return BASE_RATE.get(service)


# 127 distinct contracted rates: 118 in Appendix B, 7 substituted rates taking effect in
# 2025, and 2 services the amendment adds.
DISTINCT_RATES = len(rate_schedule) + len(substituted_rates)
print(f"Contract: {len(rate_schedule)} contracted services ({len(substituted_rates)} with a "
      f"substituted rate from {AMENDMENT_EFFECTIVE.date()}, {len(additional_services)} added by "
      f"amendment) = {DISTINCT_RATES} distinct rates; rules: {len(threshold_premiums)} premiums, "
      f"{len(weekend_uplifts)} uplifts, {len(volume_discounts)} discount tiers, {len(daily_caps)} caps, "
      f"{len(bundles)} bundles, {len(exclusion_windows)} exclusion windows "
      f"(three documents cross-checked, no conflicts)")
