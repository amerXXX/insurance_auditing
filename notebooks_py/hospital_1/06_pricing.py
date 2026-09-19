# Hospital 1 pipeline, part 6/9 — depends on parts 1-5
# (uses rate_schedule, bundles, threshold_premiums, weekend_uplifts,
# volume_discounts, line_items, half_up from 03_matching_functions.py).

# Pricing engine: bundle -> facility -> plan -> premium -> weekend uplift -> volume discount -> quantity

base_rate_map = rate_schedule.set_index("service")["base_rate_cents"].to_dict()
line_items["base_rate_cents"] = line_items["matched_service"].map(base_rate_map)

# --- (a) bundle substitution ---
bundle_map_a = {row.service_a: (row.service_b, row.bundled_rate_a_cents) for row in bundles.itertuples()}
bundle_map_b = {row.service_b: (row.service_a, row.bundled_rate_b_cents) for row in bundles.itertuples()}

_services_present = (
    line_items.dropna(subset=["matched_service", "patient_id", "service_date"])
    .groupby(["patient_id", "service_date"])["matched_service"]
    .apply(set)
)

def _bundle_rate(row):
    svc, key = row["matched_service"], (row["patient_id"], row["service_date"])
    present = _services_present.get(key, set())
    if svc in bundle_map_a and bundle_map_a[svc][0] in present:
        return bundle_map_a[svc][1]
    if svc in bundle_map_b and bundle_map_b[svc][0] in present:
        return bundle_map_b[svc][1]
    return row["base_rate_cents"]

line_items["rate_after_bundle"] = line_items.apply(_bundle_rate, axis=1)

# --- (b) facility / (c) plan-tier multipliers: both 1.0x for Hospital 1 ---
line_items["rate_after_facility_plan"] = line_items["rate_after_bundle"]

# --- (d.1) threshold premium, based on aggregate daily quantity ---
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

# --- (d.2) weekend / non-business-day uplift ---
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

# --- (e) cumulative volume discount: hospital-wide, service_date then line_id ---
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
    _apply_discount(r, p)
    for r, p in zip(line_items["rate_after_weekend"], line_items["_discount_pct"])
]

# Keep billed line totals as a provisional amount when the contract basis is not known.
line_items["expected_line_total_provisional"] = False
line_items["expected_line_total_cents"] = (
    line_items["effective_unit_rate_cents"] * line_items["billable_quantity"].astype("float64")
)
_provisional = line_items["matched_service"].isna() | line_items["malformed_service_date"]
line_items.loc[_provisional, "expected_line_total_cents"] = line_items.loc[_provisional, "line_total_cents"]
line_items.loc[_provisional, "expected_line_total_provisional"] = True

# Excluded service_a lines are not billable.
line_items.loc[line_items["exclusion_violation"], "expected_line_total_cents"] = 0
line_items.loc[line_items["exclusion_violation"], "expected_line_total_provisional"] = False

# A later duplicate of the same patient + service + service day is not separately reimbursable.
# Zero it out in the corrected total, while keeping the billed amount visible for audit evidence.
line_items.loc[line_items["cross_invoice_duplicate"], "expected_line_total_cents"] = 0
line_items.loc[line_items["cross_invoice_duplicate"], "expected_line_total_provisional"] = False

# Bundle / premium / discount diagnostic categories compare the billed rate with each stage.
line_items["bundle_applies"] = line_items.apply(
    lambda r: (
        pd.notna(r["matched_service"])
        and (r["matched_service"] in bundle_map_a or r["matched_service"] in bundle_map_b)
        and ((r["patient_id"], r["service_date"]) in _services_present.index)
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

# Premium diagnostics. A threshold premium is omitted when the billed rate is the pre-premium rate.
_premium_rate_options = {}
for service, rows in threshold_premiums.groupby("service"):
    base = int(base_rate_map[service])
    _premium_rate_options[service] = {
        half_up(Decimal(base) * (Decimal(100 + int(p)) / 100))
        for p in rows["premium_percent"]
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

# Weekend uplift diagnostics are tracked separately. The H1 labels use the broader
# premium_omitted / premium_incorrectly_applied vocabulary for this type of uplift,
# while the final prediction keeps the more precise contract wording.
_weekend_rate_options = {}
for service, rows in weekend_uplifts.groupby("service"):
    base = int(base_rate_map[service])
    _weekend_rate_options[service] = {
        half_up(Decimal(base) * (Decimal(100 + int(p)) / 100))
        for p in rows["weekend_uplift_percent"]
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

# Volume-discount diagnostics.
_discount_rate_options = {}
for service, rows in volume_discounts.groupby("service"):
    base = int(base_rate_map[service])
    _discount_rate_options[service] = {
        half_up(Decimal(base) * (Decimal(100 - int(p)) / 100))
        for p in rows["discount_percent"]
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

# unit_price_mismatch is a generic catch-all for "billed price doesn't match the
# expected rate." When a more specific rate-derived category already explains the
# same line's price delta (premium/uplift/discount omitted or misapplied), the
# generic flag is redundant and only dilutes error_category precision -- suppress it.
_rate_derived_cats = [
    "premium_omitted", "premium_incorrectly_applied",
    "weekend_uplift_omitted", "weekend_uplift_incorrectly_applied",
    "volume_discount_omitted", "volume_discount_incorrectly_applied",
]
line_items["unit_price_mismatch"] = (
    line_items["unit_price_mismatch"] & ~line_items[_rate_derived_cats].any(axis=1)
)
