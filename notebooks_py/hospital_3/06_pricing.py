# Hospital 3 pipeline, part 6/7 — depends on parts 1-5
# (uses rate_schedule, substituted_rates, bundles, threshold_premiums, weekend_uplifts,
# volume_discounts, line_items, half_up, base_rate_for).

### Pricing engine
#
# Base Agreement clause 3.2 sets the order: (a) substitution of a bundled rate; (b) the
# facility multiplier; (c) the plan-tier multiplier; (d) any premium or uplift; and (e)
# any cumulative volume discount -- the same (a)-(e) order as every other hospital here.
# Clause 1.5 makes stages (b) and (c) the identity (single facility, no facility
# differential, all plan tiers reimbursed identically). Clause 3.1 requires half-up-cent
# rounding after each individual step.
#
# What is different about Hospital 3 is the rate the order starts from. Amendment clause
# A1.1.2 applies the amendment *by Service Date*: a line whose Service Date falls on or
# after 1 January 2025 is priced under the amendment, one before it under Appendix B, and
# "The date on which an invoice is issued is irrelevant for this purpose". base_rate_for()
# in 02_contract_extraction.py resolves that per line. Amendment clause A1.4.1 confirms the
# premiums, caps, bundles, exclusion windows and calculation conventions are unchanged and
# "apply to the substituted rates in the same way as they applied to the rates they
# replace", so only stage-0 (which rate to start from) is date-dependent.

line_items["base_rate_cents"] = [
    base_rate_for(svc, sd)
    for svc, sd in zip(line_items["matched_service"], line_items["service_date"])
]
line_items["priced_under_amendment"] = [
    bool(pd.notna(sd) and sd >= AMENDMENT_EFFECTIVE and svc in SUBSTITUTED_RATE_FROM)
    for svc, sd in zip(line_items["matched_service"], line_items["service_date"])
]

# --- (a) section 8 bundle substitution: both Services, same Patient, same Service Day ---
bundle_map_a = {row.service_a: (row.service_b, row.bundled_rate_a_cents) for row in bundles.itertuples()}
bundle_map_b = {row.service_b: (row.service_a, row.bundled_rate_b_cents) for row in bundles.itertuples()}

_services_present = (
    line_items.dropna(subset=["matched_service", "patient_id", "service_date"])
    .groupby(["patient_id", "service_date"])["matched_service"]
    .apply(set)
)

def _bundle_rate(row):
    svc, key = row["matched_service"], (row["patient_id"], row["service_date"])
    if pd.isna(row["base_rate_cents"]):
        return row["base_rate_cents"]
    present = _services_present.get(key, set())
    if svc in bundle_map_a and bundle_map_a[svc][0] in present:
        return bundle_map_a[svc][1]
    if svc in bundle_map_b and bundle_map_b[svc][0] in present:
        return bundle_map_b[svc][1]
    return row["base_rate_cents"]

line_items["rate_after_bundle"] = line_items.apply(_bundle_rate, axis=1)

# --- (b)/(c) facility and plan-tier multipliers: identity for Hospital 3 (clause 1.5) ---
line_items["rate_after_facility_plan"] = line_items["rate_after_bundle"]

# --- (d.1) section 4 threshold premium, on the aggregate per Patient per Service Day ---
_premium_map = threshold_premiums.set_index("service")[["threshold_units", "premium_percent"]].to_dict("index")
line_items["_day_qty_this_service"] = line_items.groupby(
    ["patient_id", "matched_service", "service_date"]
)["quantity"].transform("sum")

line_items["premium_applies"] = False
line_items["rate_after_premium"] = line_items["rate_after_facility_plan"]
for idx, row in line_items.iterrows():
    rule = _premium_map.get(row["matched_service"])
    rate = row["rate_after_facility_plan"]
    if pd.isna(rate) or rule is None or pd.isna(row["_day_qty_this_service"]):
        continue
    if row["_day_qty_this_service"] > rule["threshold_units"]:
        line_items.at[idx, "premium_applies"] = True
        line_items.at[idx, "rate_after_premium"] = half_up(
            Decimal(rate) * (Decimal(100 + int(rule["premium_percent"])) / 100)
        )

# --- (d.2) section 5 non-business-day uplift (Business Day = not Saturday or Sunday, 2.2) ---
_weekend_map = weekend_uplifts.set_index("service")["weekend_uplift_percent"].to_dict()
_is_weekend = line_items["service_date"].dt.dayofweek >= 5
line_items["weekend_applies"] = False
line_items["rate_after_weekend"] = line_items["rate_after_premium"]
for idx, (r, s, w) in enumerate(zip(line_items["rate_after_premium"], line_items["matched_service"], _is_weekend)):
    pct = _weekend_map.get(s)
    if pd.isna(r) or pct is None or pd.isna(w) or not w:
        continue
    line_items.at[line_items.index[idx], "weekend_applies"] = True
    line_items.at[line_items.index[idx], "rate_after_weekend"] = half_up(
        Decimal(r) * (Decimal(100 + int(pct)) / 100)
    )

# --- (e) section 6 cumulative volume discount: prior-to-line, Service Date then line_id ---
line_items["_discount_pct"] = 0
for service, _ in volume_discounts.groupby("service"):
    idx = line_items.index[line_items["matched_service"] == service]
    if len(idx) == 0:
        continue
    sub = line_items.loc[idx].sort_values(["service_date", "line_id"])
    cumulative_before = sub["quantity"].cumsum() - sub["quantity"]
    tiers = volume_discounts[volume_discounts["service"] == service].sort_values("threshold_units")
    pct = pd.Series(0, index=sub.index, dtype="int64")
    for _, tier in tiers.iterrows():
        pct = pct.where(cumulative_before <= int(tier["threshold_units"]), int(tier["discount_percent"]))
    line_items.loc[sub.index, "_discount_pct"] = pct

def _apply_discount(rate, pct):
    if pd.isna(rate) or not pct:
        return rate
    return half_up(Decimal(rate) * (Decimal(100 - int(pct)) / 100))

line_items["effective_unit_rate_cents"] = [
    _apply_discount(r, p) for r, p in zip(line_items["rate_after_weekend"], line_items["_discount_pct"])
]

# Keep billed line totals as a provisional amount when the contract basis is not known.
# A Service billed before it was contracted (A1.3) has no contract rate for that Service
# Date at all, so it lands here too rather than being priced on a rate that did not exist.
line_items["expected_line_total_provisional"] = False
line_items["expected_line_total_cents"] = (
    line_items["effective_unit_rate_cents"].astype("float64")
    * line_items["billable_quantity"].astype("float64")
)
_provisional = (
    line_items["matched_service"].isna()
    | line_items["malformed_service_date"]
    | line_items["effective_unit_rate_cents"].isna()
)
line_items.loc[_provisional, "expected_line_total_cents"] = line_items.loc[_provisional, "line_total_cents"]
line_items.loc[_provisional, "expected_line_total_provisional"] = True

# Section 9 excluded service_a lines are not billable.
line_items.loc[line_items["exclusion_violation"], "expected_line_total_cents"] = 0
line_items.loc[line_items["exclusion_violation"], "expected_line_total_provisional"] = False

# Clause 10.3 later duplicate of same Patient + Service + Service Date is not billable.
line_items.loc[line_items["cross_invoice_duplicate"], "expected_line_total_cents"] = 0
line_items.loc[line_items["cross_invoice_duplicate"], "expected_line_total_provisional"] = False

# --- Diagnostic categories: compare the billed rate against each pricing stage ---
line_items["bundle_applies"] = line_items.apply(
    lambda r: (
        pd.notna(r["matched_service"])
        and (r["matched_service"] in bundle_map_a or r["matched_service"] in bundle_map_b)
        and (
            (r["matched_service"] in bundle_map_a and bundle_map_a[r["matched_service"]][0] in _services_present.get((r["patient_id"], r["service_date"]), set()))
            or (r["matched_service"] in bundle_map_b and bundle_map_b[r["matched_service"]][0] in _services_present.get((r["patient_id"], r["service_date"]), set()))
        )
    ), axis=1
)
line_items["bundle_not_applied"] = (
    line_items["bundle_applies"]
    & (line_items["unit_price_cents"] == line_items["base_rate_cents"])
    & (line_items["rate_after_bundle"] != line_items["base_rate_cents"])
)

line_items["unit_price_mismatch"] = (
    line_items["matched_service"].notna()
    & line_items["effective_unit_rate_cents"].notna()
    & (line_items["unit_price_cents"] != line_items["effective_unit_rate_cents"])
)

# Hospital 3 only: the billed price is the rate that applied on the *other* side of the
# amendment's effective date. That is a specific, nameable error -- the Provider billed a
# superseded rate (or applied the new one early) -- rather than a generic price mismatch.
_rate_before = dict(zip(substituted_rates["service"], substituted_rates["rate_before_cents"]))
_rate_from = dict(zip(substituted_rates["service"], substituted_rates["rate_from_cents"]))
line_items["wrong_rate_period"] = [
    bool(
        pd.notna(svc) and svc in _rate_from and pd.notna(sd)
        and billed != effective
        and billed == (_rate_before[svc] if sd >= AMENDMENT_EFFECTIVE else _rate_from[svc])
    )
    for svc, sd, billed, effective in zip(
        line_items["matched_service"], line_items["service_date"],
        line_items["unit_price_cents"], line_items["effective_unit_rate_cents"],
    )
]

_premium_rate_options = {}
for service, rows in threshold_premiums.groupby("service"):
    bases = {BASE_RATE.get(service)} | ({_rate_from[service]} if service in _rate_from else set())
    _premium_rate_options[service] = {
        half_up(Decimal(int(b)) * (Decimal(100 + int(p)) / 100))
        for b in bases if b is not None for p in rows["premium_percent"]
    }
line_items["premium_omitted"] = (
    line_items["premium_applies"]
    & (line_items["unit_price_cents"] == line_items["rate_after_facility_plan"])
    & (line_items["unit_price_cents"] != line_items["effective_unit_rate_cents"])
)
line_items["premium_incorrectly_applied"] = line_items.apply(
    lambda r: (
        pd.notna(r["matched_service"])
        and (r["unit_price_cents"] != r["effective_unit_rate_cents"])
        and (
            (bool(r["premium_applies"]) and not bool(r["premium_omitted"])
             and r["unit_price_cents"] in _premium_rate_options.get(r["matched_service"], set()))
            or (not bool(r["premium_applies"])
                and int(r["unit_price_cents"]) in _premium_rate_options.get(r["matched_service"], set()))
        )
    ), axis=1
)

_weekend_rate_options = {}
for service, rows in weekend_uplifts.groupby("service"):
    bases = {BASE_RATE.get(service)} | ({_rate_from[service]} if service in _rate_from else set())
    _weekend_rate_options[service] = {
        half_up(Decimal(int(b)) * (Decimal(100 + int(p)) / 100))
        for b in bases if b is not None for p in rows["weekend_uplift_percent"]
    }
line_items["weekend_uplift_omitted"] = (
    line_items["weekend_applies"]
    & (line_items["unit_price_cents"] == line_items["rate_after_premium"])
    & (line_items["unit_price_cents"] != line_items["effective_unit_rate_cents"])
)
line_items["weekend_uplift_incorrectly_applied"] = line_items.apply(
    lambda r: (
        pd.notna(r["matched_service"])
        and (r["unit_price_cents"] != r["effective_unit_rate_cents"])
        and (not bool(r["weekend_applies"]))
        and (int(r["unit_price_cents"]) in _weekend_rate_options.get(r["matched_service"], set()))
    ), axis=1
)

_discount_rate_options = {}
for service, rows in volume_discounts.groupby("service"):
    bases = {BASE_RATE.get(service)} | ({_rate_from[service]} if service in _rate_from else set())
    _discount_rate_options[service] = {
        half_up(Decimal(int(b)) * (Decimal(100 - int(p)) / 100))
        for b in bases if b is not None for p in rows["discount_percent"]
    }
line_items["volume_discount_omitted"] = (
    (line_items["_discount_pct"] > 0)
    & (line_items["unit_price_cents"] == line_items["rate_after_weekend"])
    & (line_items["unit_price_cents"] != line_items["effective_unit_rate_cents"])
)
line_items["volume_discount_incorrectly_applied"] = line_items.apply(
    lambda r: (
        pd.notna(r["matched_service"])
        and (r["unit_price_cents"] != r["effective_unit_rate_cents"])
        and (
            ((int(r["_discount_pct"]) > 0) and not bool(r["volume_discount_omitted"]))
            or ((int(r["_discount_pct"]) == 0) and int(r["unit_price_cents"]) in _discount_rate_options.get(r["matched_service"], set()))
        )
    ), axis=1
)

# The generic unit_price_mismatch is suppressed where a more specific rate-derived
# category already explains the same line's delta (same rule as the other hospitals,
# extended here to Hospital 3's wrong_rate_period).
_rate_derived_cats = [
    "premium_omitted", "premium_incorrectly_applied",
    "weekend_uplift_omitted", "weekend_uplift_incorrectly_applied",
    "volume_discount_omitted", "volume_discount_incorrectly_applied",
    "wrong_rate_period",
]
line_items["unit_price_mismatch"] = (
    line_items["unit_price_mismatch"] & ~line_items[_rate_derived_cats].any(axis=1)
)
