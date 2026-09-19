# Hospital 5 pipeline, part 6/7 — depends on parts 1-5
# (uses rate_schedule, bundles, threshold_premiums, weekend_uplifts, volume_discounts,
# FACILITY_MULTIPLIER, TIER_MULTIPLIER, line_items, half_up).

### Pricing engine
#
# Clause 3.1 sets the order explicitly: (a) substitution of a bundled rate; (b) the
# facility multiplier; (c) the plan-tier multiplier; (d) any premium or uplift; and
# (e) any cumulative volume discount. Clause 3.2 requires half-up-cent rounding after
# each individual step, not once at the end, and clause 3.4 notes a multiplier of 1.0
# still takes the rounding step. That is the same (a)-(e) order Hospitals 1 and 4 use,
# so the engine's shape is reused -- but stages (b) and (c) do real work here for the
# first time, since Tables 2 and 3 vary by service.
#
# Clause 3.1 groups "any premium or uplift" into a single stage (d). Section 5 threshold
# premiums and Section 6 non-business-day uplifts are applied in that order within the
# stage, the same convention Hospital 1 used where both existed.
#
# A line whose service could not be matched, whose service date is malformed, or whose
# facility code or plan tier is not one the contract recognises cannot be priced from the
# contract at all. Rather than dropping or inventing a figure, the billed line total is
# carried through as a *provisional* expected amount and confidence is lowered downstream
# -- the same policy as Hospitals 1 and 4.

base_rate_map = rate_schedule.set_index("service")["base_rate_cents"].to_dict()
line_items["base_rate_cents"] = line_items["matched_service"].map(base_rate_map)

# --- (a) Section 7 bundle substitution ---
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

# --- (d) stage inputs: which premium / uplift / discount applies to each line ---

# Section 5: assessed against the aggregate quantity of the Service delivered to the
# Patient on the Service Day, across all line items and all invoices (clause 5.1).
_premium_map = threshold_premiums.set_index("service")[["threshold_units", "premium_percent"]].to_dict("index")
line_items["_day_qty_this_service"] = line_items.groupby(
    ["patient_id", "matched_service", "service_date"]
)["quantity"].transform("sum")
line_items["_premium_pct"] = 0
line_items["premium_applies"] = False
for idx, row in line_items.iterrows():
    rule = _premium_map.get(row["matched_service"])
    if rule is None or pd.isna(row["_day_qty_this_service"]):
        continue
    if row["_day_qty_this_service"] > rule["threshold_units"]:
        line_items.at[idx, "premium_applies"] = True
        line_items.at[idx, "_premium_pct"] = int(rule["premium_percent"])

# Section 6: non-business day means a Saturday or Sunday (clause 2.2).
_weekend_map = weekend_uplifts.set_index("service")["weekend_uplift_percent"].to_dict()
_is_weekend = line_items["service_date"].dt.dayofweek >= 5
line_items["_weekend_pct"] = [
    int(_weekend_map.get(svc, 0)) if (pd.notna(w) and bool(w)) else 0
    for svc, w in zip(line_items["matched_service"], _is_weekend)
]
line_items["weekend_applies"] = line_items["_weekend_pct"] > 0

# Section 8: cumulative utilisation across the whole term, aggregated across all Patients,
# in Service Date then line-ID order; the discount applies to units *after* the line on
# which the threshold is crossed (clause 8.1). Where two thresholds are met, the deeper
# discount applies.
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


def chain_rate(start_rate, facility_multiplier, tier_multiplier, premium_pct, weekend_pct, discount_pct):
    """Clause 3.3 in full: (b) facility, (c) plan tier, (d) premium/uplift, (e) discount.

    Half-up rounding to the whole cent after each individual step (clause 3.2).
    """
    if pd.isna(start_rate):
        return None
    rate = half_up(Decimal(int(start_rate)) * Decimal(facility_multiplier))
    rate = half_up(Decimal(rate) * Decimal(tier_multiplier))
    if premium_pct:
        rate = half_up(Decimal(rate) * (Decimal(100 + int(premium_pct)) / 100))
    if weekend_pct:
        rate = half_up(Decimal(rate) * (Decimal(100 + int(weekend_pct)) / 100))
    if discount_pct:
        rate = half_up(Decimal(rate) * (Decimal(100 - int(discount_pct)) / 100))
    return rate


def line_rate(row, facility_code=None, tier=None):
    """Effective unit rate for a line, optionally under a hypothetical facility / tier."""
    svc = row["matched_service"]
    if pd.isna(svc) or pd.isna(row["rate_after_bundle"]):
        return None
    facility_code = facility_code or row["facility_code"]
    tier = tier or row["plan_tier"]
    facility_multiplier = FACILITY_MULTIPLIER.get((svc, facility_code))
    tier_multiplier = TIER_MULTIPLIER.get((svc, tier))
    if facility_multiplier is None or tier_multiplier is None:
        return None
    return chain_rate(
        row["rate_after_bundle"], facility_multiplier, tier_multiplier,
        row["_premium_pct"], row["_weekend_pct"], row["_discount_pct"],
    )


# --- stage-by-stage rates, kept as columns so the diagnostics can compare against them ---
_stage_rows = []
for row in line_items.to_dict("records"):
    svc = row["matched_service"]
    start = row["rate_after_bundle"]
    if pd.isna(svc) or pd.isna(start):
        _stage_rows.append((None, None, None, None, None))
        continue
    facility_multiplier = FACILITY_MULTIPLIER.get((svc, row["facility_code"]))
    tier_multiplier = TIER_MULTIPLIER.get((svc, row["plan_tier"]))
    if facility_multiplier is None or tier_multiplier is None:
        _stage_rows.append((None, None, None, None, None))
        continue
    after_facility = half_up(Decimal(int(start)) * Decimal(facility_multiplier))
    after_tier = half_up(Decimal(after_facility) * Decimal(tier_multiplier))
    after_premium = after_tier
    if row["_premium_pct"]:
        after_premium = half_up(Decimal(after_tier) * (Decimal(100 + int(row["_premium_pct"])) / 100))
    after_weekend = after_premium
    if row["_weekend_pct"]:
        after_weekend = half_up(Decimal(after_premium) * (Decimal(100 + int(row["_weekend_pct"])) / 100))
    effective = after_weekend
    if row["_discount_pct"]:
        effective = half_up(Decimal(after_weekend) * (Decimal(100 - int(row["_discount_pct"])) / 100))
    _stage_rows.append((after_facility, after_tier, after_premium, after_weekend, effective))

line_items["rate_after_facility"] = [r[0] for r in _stage_rows]
line_items["rate_after_plan"] = [r[1] for r in _stage_rows]
line_items["rate_after_premium"] = [r[2] for r in _stage_rows]
line_items["rate_after_weekend"] = [r[3] for r in _stage_rows]
line_items["effective_unit_rate_cents"] = [r[4] for r in _stage_rows]

# Keep billed line totals as a provisional amount when the contract basis is not known.
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

# Clause 10.3 later duplicate of same patient + service + Service Day is not separately reimbursable.
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

# Premium / uplift / discount diagnostics: was the stage omitted, or applied when it
# should not have been? Each compares the billed price against the rate that stage would
# have produced, holding the rest of the chain at its correct value.
def _stage_flags(row):
    svc = row["matched_service"]
    billed = row["unit_price_cents"]
    effective = row["effective_unit_rate_cents"]
    if pd.isna(svc) or effective is None or pd.isna(effective) or billed == effective:
        return pd.Series({
            "premium_omitted": False, "premium_incorrectly_applied": False,
            "weekend_uplift_omitted": False, "weekend_uplift_incorrectly_applied": False,
            "volume_discount_omitted": False, "volume_discount_incorrectly_applied": False,
            "facility_multiplier_misapplied": False, "plan_tier_multiplier_misapplied": False,
        })

    premium_rule = _premium_map.get(svc)
    premium_pct = int(premium_rule["premium_percent"]) if premium_rule else 0
    weekend_pct = int(_weekend_map.get(svc, 0))
    discount_pcts = sorted({int(p) for p in volume_discounts.loc[
        volume_discounts["service"] == svc, "discount_percent"]})

    facility_multiplier = FACILITY_MULTIPLIER.get((svc, row["facility_code"]))
    tier_multiplier = TIER_MULTIPLIER.get((svc, row["plan_tier"]))
    if facility_multiplier is None or tier_multiplier is None:
        return pd.Series({
            "premium_omitted": False, "premium_incorrectly_applied": False,
            "weekend_uplift_omitted": False, "weekend_uplift_incorrectly_applied": False,
            "volume_discount_omitted": False, "volume_discount_incorrectly_applied": False,
            "facility_multiplier_misapplied": False, "plan_tier_multiplier_misapplied": False,
        })

    def rate(premium, weekend, discount, fac=facility_multiplier, tier=tier_multiplier):
        return chain_rate(row["rate_after_bundle"], fac, tier, premium, weekend, discount)

    applied_premium, applied_weekend = row["_premium_pct"], row["_weekend_pct"]
    applied_discount = row["_discount_pct"]

    # Stage omitted: the billed price is what you get with that stage left out.
    premium_omitted = bool(applied_premium) and billed == rate(0, applied_weekend, applied_discount)
    weekend_omitted = bool(applied_weekend) and billed == rate(applied_premium, 0, applied_discount)
    discount_omitted = bool(applied_discount) and billed == rate(applied_premium, applied_weekend, 0)

    # Stage applied when it should not have been (or at the wrong size).
    premium_wrong = (not applied_premium) and premium_pct and billed == rate(premium_pct, applied_weekend, applied_discount)
    weekend_wrong = (not applied_weekend) and weekend_pct and billed == rate(applied_premium, weekend_pct, applied_discount)
    discount_wrong = any(
        billed == rate(applied_premium, applied_weekend, d)
        for d in discount_pcts if d != applied_discount
    )

    # Wrong multiplier: the billed price matches the chain run with a different facility
    # or a different plan tier than the invoice records.
    facility_wrong = any(
        billed == rate(applied_premium, applied_weekend, applied_discount,
                       fac=FACILITY_MULTIPLIER[(svc, code)])
        for code in FACILITY_CODES if code != row["facility_code"]
    )
    tier_wrong = any(
        billed == rate(applied_premium, applied_weekend, applied_discount,
                       tier=TIER_MULTIPLIER[(svc, t)])
        for t in PLAN_TIERS if t != row["plan_tier"]
    )

    return pd.Series({
        "premium_omitted": bool(premium_omitted),
        "premium_incorrectly_applied": bool(premium_wrong),
        "weekend_uplift_omitted": bool(weekend_omitted),
        "weekend_uplift_incorrectly_applied": bool(weekend_wrong),
        "volume_discount_omitted": bool(discount_omitted),
        "volume_discount_incorrectly_applied": bool(discount_wrong),
        "facility_multiplier_misapplied": bool(facility_wrong),
        "plan_tier_multiplier_misapplied": bool(tier_wrong),
    })

line_items = line_items.join(line_items.apply(_stage_flags, axis=1))

# unit_price_mismatch is a generic catch-all for "billed price doesn't match the
# expected rate." When a more specific rate-derived category already explains the
# same line's price delta, the generic flag is redundant and only dilutes
# error_category precision -- suppress it. (Same rule as Hospitals 1 and 4, extended
# to Hospital 5's two multiplier categories.)
_rate_derived_cats = [
    "premium_omitted", "premium_incorrectly_applied",
    "weekend_uplift_omitted", "weekend_uplift_incorrectly_applied",
    "volume_discount_omitted", "volume_discount_incorrectly_applied",
    "facility_multiplier_misapplied", "plan_tier_multiplier_misapplied",
]
line_items["unit_price_mismatch"] = (
    line_items["unit_price_mismatch"] & ~line_items[_rate_derived_cats].any(axis=1)
)
