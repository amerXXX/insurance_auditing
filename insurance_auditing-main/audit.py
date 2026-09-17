# audit.py — corrected Hospital-1 pipeline
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
import re
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent
CONTRACT_START = pd.Timestamp("2024-01-01")
CONTRACT_END   = pd.Timestamp("2025-12-31")
CONTRACT_NUMBER = "INS-H1-2024-0417"


def half_up(x):
    return int(Decimal(x).to_integral_value(rounding=ROUND_HALF_UP))


# ---------- contract parsing (identical shape to notebook, unchanged) ----------
def parse_rate_schedule(path):
    ...  # unchanged from notebook Section 4 extraction

def parse_section_5(path): ...   # threshold premiums
def parse_section_6(path): ...   # weekend uplifts
def parse_section_7(path): ...   # volume discounts
def parse_section_8(path): ...   # daily caps
def parse_section_9(path): ...   # bundles
def parse_section_10(path): ...  # exclusion windows


# ---------- service matching: text only, no price evidence ----------
# The only change vs the notebook is that `resolved_by_price` is gone.
# Ties go to needs_review. This avoids the circularity of using a
# potentially-erroneous billed amount to identify the service.
def match_all_descriptions(line_items, rate_schedule):
    ...


def main():
    invoices = pd.read_csv(
        REPO_ROOT / "invoices" / "hospital_1_invoices.csv",
        parse_dates=["invoice_date"],
    )
    line_items = pd.read_csv(REPO_ROOT / "invoices" / "hospital_1_line_items.csv")

    cpath = REPO_ROOT / "contracts" / "hospital_1" / "provider_services_agreement.md"
    rate_schedule     = parse_rate_schedule(cpath)
    threshold_premiums = parse_section_5(cpath)
    weekend_uplifts   = parse_section_6(cpath)
    volume_discounts  = parse_section_7(cpath)
    daily_caps        = parse_section_8(cpath)
    bundles           = parse_section_9(cpath)
    exclusion_windows = parse_section_10(cpath)

    # ---- service identity ----
    matches = match_all_descriptions(line_items, rate_schedule)
    line_items = line_items.merge(
        matches[["description", "matched_service", "match_status"]],
        on="description", how="left", validate="many_to_one",
    )

    # ---- dates ----
    line_items["service_date_parsed"] = pd.to_datetime(
        line_items["service_date"], format="%Y-%m-%d", errors="coerce"
    )

    # ---- occurrence rank for reused invoice IDs (unchanged) ----
    line_items["line_group_num"] = (
        line_items["line_id"].astype(str).str.extract(r"^H1-L(\d+)-", expand=False).astype("Int64")
    )
    invoices["_row_order"] = range(len(invoices))
    invoices["occurrence_rank"] = (
        invoices.sort_values(["invoice_id", "invoice_date", "_row_order"])
        .groupby("invoice_id").cumcount()
    )
    group_meta = (
        line_items.groupby(["invoice_id", "line_group_num"], dropna=False)
        .agg(group_billed_total_cents=("line_total_cents", "sum")).reset_index()
    )
    group_meta["group_rank"] = (
        group_meta.sort_values(["invoice_id", "line_group_num"])
        .groupby("invoice_id").cumcount()
    )
    line_items = line_items.merge(
        group_meta[["invoice_id", "line_group_num", "group_rank"]],
        on=["invoice_id", "line_group_num"], how="left",
    )
    line_items["occurrence_rank"] = line_items["group_rank"].astype(int)

    occ_cols = ["invoice_id", "occurrence_rank", "invoice_date", "patient_id",
                "facility_code", "plan_tier", "contract_number", "invoice_total_cents"]
    line_items = line_items.merge(
        invoices[occ_cols], on=["invoice_id", "occurrence_rank"], how="left",
        validate="many_to_one",
    )

    # ============================================================
    # STEP 1 — NON-BILLABLE identification (BEFORE caps/discounts/bundles)
    # ============================================================
    li = line_items
    li["malformed_date"]      = li["service_date_parsed"].isna()
    li["out_of_window"]       = (~li["malformed_date"]) & (
        (li["service_date_parsed"] < CONTRACT_START) | (li["service_date_parsed"] > CONTRACT_END)
    )
    li["after_invoice_date"]  = (~li["malformed_date"]) & (
        li["service_date_parsed"] > li["invoice_date"]
    )

    # Exclusion windows — service_a is non-billable within window of service_b,
    # same patient, in either direction (clause 10.1).
    li["exclusion_violation"] = False
    prelim_eligible = li[~li["malformed_date"] & li["matched_service"].notna()]
    for _, rule in exclusion_windows.iterrows():
        a = prelim_eligible[prelim_eligible["matched_service"] == rule["service_a"]]
        b = prelim_eligible[prelim_eligible["matched_service"] == rule["service_b"]]
        if a.empty or b.empty:
            continue
        pairs = a[["patient_id", "service_date_parsed"]].reset_index().merge(
            b[["patient_id", "service_date_parsed"]].reset_index(),
            on="patient_id", suffixes=("_a", "_b"),
        )
        delta = (pairs["service_date_parsed_a"] - pairs["service_date_parsed_b"]).abs().dt.days
        hits = pairs[delta <= int(rule["window_days"])]
        li.loc[hits["index_a"], "exclusion_violation"] = True

    # Cross-invoice duplicates — clause 11.4.
    # Convention: the later occurrence (by invoice_date, then line_id) is the
    # erroneous one; earlier lines stay billable. Documented in decision log.
    li["cross_invoice_duplicate"] = False
    dup_key = ["patient_id", "matched_service", "service_date_parsed"]
    for _, grp in li[li["matched_service"].notna() & ~li["malformed_date"]].groupby(dup_key, dropna=False):
        if len(grp) < 2:
            continue
        ordered = grp.sort_values(["invoice_date", "line_id"])
        li.loc[ordered.index[1:], "cross_invoice_duplicate"] = True

    li["non_billable"] = (
        li["malformed_date"]
        | li["out_of_window"]
        | li["after_invoice_date"]
        | li["exclusion_violation"]
        | li["cross_invoice_duplicate"]
    )

    # ELIGIBLE = line can be priced at contract rate.
    # Malformed/out-of-window/after-date are *flagged* but carry billed amount
    # through as a provisional expected (matches H1 label convention).
    li["eligible"] = ~li["non_billable"] & li["matched_service"].notna()

    # ============================================================
    # STEP 2 — DAILY CAPS, applied only to ELIGIBLE lines
    # Allocation convention: line_id ascending (documented; contract silent).
    # ============================================================
    cap_map = daily_caps.set_index("service")["maximum_units_per_patient_day"].to_dict()
    sub = li[li["eligible"]].sort_values(
        ["patient_id", "matched_service", "service_date_parsed", "line_id"]
    ).copy()
    sub["_prior"] = sub.groupby(["patient_id", "matched_service", "service_date_parsed"])["quantity"].cumsum() - sub["quantity"]
    sub["_cap"]   = sub["matched_service"].map(cap_map)
    sub["_bill"]  = sub["quantity"]
    m = sub["_cap"].notna()
    sub.loc[m, "_bill"] = (
        sub.loc[m, "quantity"]
        .where(sub.loc[m, "_prior"] < sub.loc[m, "_cap"], 0)
        .clip(upper=sub.loc[m, "_cap"] - sub.loc[m, "_prior"])
        .clip(lower=0)
    )
    li["billable_quantity"] = 0
    li.loc[sub.index, "billable_quantity"] = sub["_bill"].astype(int)
    li["daily_cap_exceeded"] = li["eligible"] & (li["billable_quantity"] < li["quantity"])

    # ============================================================
    # STEP 3 — BUNDLE substitution, only if BOTH services are ELIGIBLE
    # ============================================================
    eligible_sets = (
        li[li["eligible"]]
        .groupby(["patient_id", "service_date_parsed"])["matched_service"].apply(set)
    )
    bundle_lookup = {}
    for row in bundles.itertuples():
        bundle_lookup[(row.service_a, row.service_b)] = row
        bundle_lookup[(row.service_b, row.service_a)] = row

    def bundle_rate(row):
        if pd.isna(row["matched_service"]) or pd.isna(row["service_date_parsed"]):
            return None, None
        key = (row["patient_id"], row["service_date_parsed"])
        present = eligible_sets.get(key, set())
        for (a, b), rec in bundle_lookup.items():
            if row["matched_service"] == a and b in present:
                rate = rec.bundled_rate_a_cents if a == rec.service_a else rec.bundled_rate_b_cents
                return rate, True
        return None, False

    rates = li.apply(bundle_rate, axis=1, result_type="expand")
    li["bundle_rate_cents"] = rates[0]
    li["bundle_applies"]    = rates[1].fillna(False).astype(bool)

    # ============================================================
    # STEP 4 — THRESHOLD PREMIUM
    # Trigger: aggregate ELIGIBLE daily quantity of the service for the patient
    # exceeds the threshold. Uplift is then applied to every billable unit of
    # that service on that day. Documented interpretation of clause 5.1.
    # ============================================================
    prem_map = threshold_premiums.set_index("service")[["threshold_units", "premium_percent"]].to_dict("index")
    day_qty = (
        li[li["eligible"]]
        .groupby(["patient_id", "matched_service", "service_date_parsed"])["quantity"]
        .sum().rename("day_qty_eligible")
    )
    li = li.merge(day_qty.reset_index(),
                  on=["patient_id", "matched_service", "service_date_parsed"], how="left")
    li["day_qty_eligible"] = li["day_qty_eligible"].fillna(0).astype(int)

    li["premium_percent"] = li["matched_service"].map(
        lambda s: prem_map.get(s, {}).get("premium_percent")
    )
    li["premium_threshold"] = li["matched_service"].map(
        lambda s: prem_map.get(s, {}).get("threshold_units")
    )
    li["premium_applies"] = (
        li["eligible"]
        & li["premium_percent"].notna()
        & (li["day_qty_eligible"] > li["premium_threshold"])
    )

    # ============================================================
    # STEP 5 — WEEKEND UPLIFT
    # Clause 6: non-Business Day. Sat/Sun by clause 2.2.
    # ============================================================
    wk_map = weekend_uplifts.set_index("service")["weekend_uplift_percent"].to_dict()
    li["weekend_percent"] = li["matched_service"].map(wk_map)
    is_weekend = li["service_date_parsed"].dt.dayofweek >= 5
    li["weekend_applies"] = li["eligible"] & li["weekend_percent"].notna() & is_weekend

    # ============================================================
    # STEP 6 — CUMULATIVE VOLUME DISCOUNT
    # Clause 7.1/7.2: cumulative utilisation across all patients,
    # by Service Date then line_id; discount applies where cumulative
    # PRIOR exceeds the threshold. Use BILLABLE quantity (the fix).
    # ============================================================
    li["_discount_pct"] = 0
    for service, tiers in volume_discounts.groupby("service"):
        idx = li.index[(li["matched_service"] == service) & li["eligible"]]
        if len(idx) == 0:
            continue
        sub2 = li.loc[idx].sort_values(["service_date_parsed", "line_id"])
        cum_before = sub2["billable_quantity"].cumsum() - sub2["billable_quantity"]
        pct = pd.Series(0, index=sub2.index, dtype="int64")
        for _, tier in tiers.sort_values("threshold_units").iterrows():
            pct = pct.where(cum_before <= int(tier["threshold_units"]),
                            int(tier["discount_percent"]))
        li.loc[sub2.index, "_discount_pct"] = pct

    # ============================================================
    # STEP 7 — LINE PRICING (clause 3.2 order; half-up after each step)
    # ============================================================
    base_map = rate_schedule.set_index("service")["base_rate_cents"].to_dict()
    li["base_rate_cents"] = li["matched_service"].map(base_map)

    def price_line(row):
        if not row["eligible"]:
            return 0                      # exclusion / duplicate / non-billable
        if pd.isna(row["matched_service"]):
            return int(row["line_total_cents"])   # provisional, billed carried through
        rate = row["base_rate_cents"]
        if row["bundle_applies"] and not pd.isna(row["bundle_rate_cents"]):
            rate = int(row["bundle_rate_cents"])
        # facility = plan = 1x for H1 (clause 1.2, 1.3)
        if row["premium_applies"]:
            rate = half_up(Decimal(rate) * (Decimal(100 + int(row["premium_percent"])) / 100))
        if row["weekend_applies"]:
            rate = half_up(Decimal(rate) * (Decimal(100 + int(row["weekend_percent"])) / 100))
        if row["_discount_pct"] > 0:
            rate = half_up(Decimal(rate) * (Decimal(100 - int(row["_discount_pct"])) / 100))
        return rate * int(row["billable_quantity"])

    li["expected_line_total_cents"] = li.apply(price_line, axis=1)
    li["expected_line_provisional"] = (
        ~li["eligible"] & ~(li["exclusion_violation"] | li["cross_invoice_duplicate"])
    )

    # ============================================================
    # STEP 8 — Aggregate to invoice occurrence, then one row per invoice_id
    # ============================================================
    occ = li.groupby(["invoice_id", "occurrence_rank"]).agg(
        expected_total_cents=("expected_line_total_cents", "sum"),
        any_provisional=("expected_line_provisional", "any"),
    ).reset_index()

    # invoice-level checks (11.1, 11.2)
    invoices["contract_number_mismatch"] = invoices["contract_number"] != CONTRACT_NUMBER
    invoices["duplicate_invoice_id"] = invoices["invoice_id"].duplicated(keep=False)

    # occurrence-level flag roll-ups
    def rollup(col):
        return li.groupby(["invoice_id", "occurrence_rank"])[col].any().rename(col).reset_index()

    flags = [
        "malformed_date", "out_of_window", "after_invoice_date",
        "exclusion_violation", "cross_invoice_duplicate", "daily_cap_exceeded",
        "premium_applies", "weekend_applies",
    ]
    flag_df = None
    for c in flags:
        f = rollup(c)
        flag_df = f if flag_df is None else flag_df.merge(f, on=["invoice_id", "occurrence_rank"])

    # unmatched → unknown_service flag
    unmatched = (li["matched_service"].isna()).groupby(
        [li["invoice_id"], li["occurrence_rank"]]
    ).any().rename("unknown_service").reset_index()
    flag_df = flag_df.merge(unmatched, on=["invoice_id", "occurrence_rank"], how="left")

    occ = (occ
           .merge(flag_df, on=["invoice_id", "occurrence_rank"], how="left")
           .merge(invoices[["invoice_id", "occurrence_rank", "invoice_date", "invoice_total_cents",
                            "contract_number_mismatch", "duplicate_invoice_id"]],
                  on=["invoice_id", "occurrence_rank"], how="left"))

    # choose the later occurrence for reused IDs (matches H1 labels)
    occ["selected"] = occ["occurrence_rank"] == occ.groupby("invoice_id")["occurrence_rank"].transform("max")
    invoice_summary = occ[occ["selected"]].sort_values("invoice_id").reset_index(drop=True)

    # error category
    def category(row):
        cats = []
        for c in ["malformed_date", "out_of_window", "after_invoice_date",
                  "exclusion_violation", "cross_invoice_duplicate", "daily_cap_exceeded",
                  "unknown_service", "contract_number_mismatch", "duplicate_invoice_id"]:
            if bool(row.get(c, False)):
                cats.append({
                    "malformed_date": "malformed_service_date",
                    "out_of_window": "service_date_out_of_window",
                    "after_invoice_date": "service_date_after_invoice_date",
                    "exclusion_violation": "exclusion_window_violation",
                    "cross_invoice_duplicate": "cross_invoice_duplicate",
                    "daily_cap_exceeded": "daily_cap_exceeded",
                    "unknown_service": "unknown_service",
                    "contract_number_mismatch": "contract_number_mismatch",
                    "duplicate_invoice_id": "duplicate_invoice_id",
                }[c])
        return "|".join(cats)

    invoice_summary["error_category"] = invoice_summary.apply(category, axis=1)
    invoice_summary["flagged"] = (invoice_summary["error_category"] != "").astype(int)

    # confidence — same policy as before, but now honest about provisional
    def conf(row):
        c = 0.95
        if row["unknown_service"]:
            c = min(c, 0.35)
        if row["any_provisional"]:
            c = min(c, 0.55)
        if row["duplicate_invoice_id"]:
            c = min(c, 0.55)
        if row["daily_cap_exceeded"]:
            c = min(c, 0.75)
        if row["exclusion_violation"]:
            c = min(c, 0.85)
        return round(float(c), 2)

    invoice_summary["confidence"] = invoice_summary.apply(conf, axis=1)
    invoice_summary["billed_total_cents"] = invoice_summary["invoice_total_cents"]
    invoice_summary["expected_total_cents"] = invoice_summary["expected_total_cents"].round().astype("Int64")

    out = invoice_summary[[
        "invoice_id", "flagged", "error_category",
        "expected_total_cents", "billed_total_cents", "confidence",
    ]]
    out.to_csv(REPO_ROOT / "hospital_1_dev_predictions.csv", index=False)
    return out


if __name__ == "__main__":
    main()