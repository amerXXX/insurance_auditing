# Hospital 2 pipeline, part 3/7 — depends on 01_setup.py and 02_contract_extraction.py
# (uses line_items, rate_schedule, threshold_premiums, weekend_uplifts, volume_discounts,
# bundles).

### Service matching
#
# Hospital 2's billing descriptions use the same abbreviation conventions and free-text
# style as the other hospitals (this is the same synthetic generator), so the matcher, its
# alias tables and its conservative acceptance thresholds (MIN_SCORE=0.55,
# GAP_THRESHOLD=0.08) are reused verbatim rather than re-tuned.
#
# Article XXIII (Coding and Description Practice) and the closing sentence of every
# service clause both make the same point in prose: "The description applied by the
# Provider on any invoice shall not of itself vary the rate applicable to this Service;
# the rate follows the Service actually delivered." That is the contract explicitly saying
# the free-text description is evidence of identity, not a rate in its own right -- which
# is exactly the policy the matcher already implements: resolve the description to a
# contracted Service, then price the Service, never the description.
#
# plausible_unit_prices() models the prices a line of a given service could legitimately
# carry, used only as secondary evidence to break a text tie. Hospital 2's clause 1.3
# removes both multipliers, so the set is base (or bundled substitute) plus premium,
# uplift and discount variants.

REF_CODE_RE = re.compile(r"/[A-Z]{1,4}-?\d+\s*$")

TOKEN_ALIASES = {
    # Generic billing abbreviations
    "adv": "advanced", "asst": "assisted", "amb": "ambulatory", "inpt": "inpatient",
    "outpt": "outpatient", "obs": "observation", "spclst": "specialist", "supv": "supervised",
    "rtn": "routine", "std": "standard", "cont": "continuous", "interm": "intermittent",
    "proc": "procedure", "procure": "procedure", "sess": "session", "svc": "service",
    "prog": "programme", "physio": "physiotherapy", "occ": "occupancy", "rm": "room",
    "cs": "case", "conf": "conference", "wd": "ward", "bd": "bed", "anaes": "anaesthesia",
    "anaest": "anaesthesia", "anest": "anaesthesia", "admin": "administration",
    "spcm": "specimen", "anly": "analysis", "pnl": "panel", "plng": "planning",
    "disp": "dispensing", "pharm": "pharmaceutical", "radiother": "radiotherapy",
    "radioth": "radiotherapy", "biop": "biopsy", "dial": "dialysis", "transf": "transfusion",
    "crit": "critical", "cr": "critical", "nutr": "nutritional", "wnd": "wound",
    "rehab": "rehabilitation", "vent": "ventilation", "tele": "telemetry", "img": "imaging",
    "diag": "diagnostic", "isom": "isolation", "paed": "paediatric", "paeds": "paediatric",
    "intens": "intensive", "transp": "transport", "recov": "recovery", "steril": "sterilisation",
    "foc": "focused", "elect": "elective", "emer": "emergency", "postop": "postoperative",
    "preop": "preoperative", "lab": "laboratory", "nurs": "nursing", "consult": "consultation",
    "endosc": "endoscopic", "interp": "interpretation", "fract": "fraction",
    # Clinical / specialty abbreviations
    "ent": "otolaryngologic", "gi": "gastrointestinal", "ortho": "orthopaedic",
    "ophth": "ophthalmic", "haem": "haematology", "hema": "haematology", "neuro": "neurological",
    "rheum": "rheumatologic", "urol": "urologic", "pulm": "pulmonary", "psych": "psychiatric",
    "ger": "geriatric", "onco": "oncology", "onc": "oncology", "derm": "dermatologic", "hep": "hepatic",
    "vasc": "vascular", "endo": "endocrine", "obst": "obstetric", "immun": "immunologic",
    "ren": "renal",
    "infect": "infectious", "msk": "musculoskeletal", "musk": "musculoskeletal", "pall": "palliative",
    "card": "cardiac", "metab": "metabolic",
}

CLINICAL_ANCHORS = {
    "cardiac", "haematology", "infectious", "metabolic", "neurological", "rheumatologic",
    "ophthalmic", "immunologic", "musculoskeletal", "gastrointestinal", "geriatric", "urologic",
    "pulmonary", "psychiatric", "oncology", "otolaryngologic", "palliative", "renal", "vascular",
    "dermatologic", "paediatric", "endocrine", "obstetric", "hepatic", "orthopaedic"
}

SERVICE_CLASS_ALIASES = {
    "specimen": {"specimen", "analysis", "panel", "laboratory", "lab"},
    "analysis": {"specimen", "analysis", "panel", "laboratory", "lab"},
    "panel": {"specimen", "analysis", "panel", "laboratory", "lab"},
    "dialysis": {"dialysis"},
    "wound": {"wound", "care"},
    "rehabilitation": {"rehabilitation", "programme"},
    "consultation": {"consultation"},
    "transport": {"transport"},
    "occupancy": {"occupancy", "room", "bed", "ward"},
    "endoscopic": {"endoscopic", "procedure"},
    "radiotherapy": {"radiotherapy", "fraction"},
    "infusion": {"infusion", "therapy"},
    "discharge": {"discharge", "planning"},
    "pharmaceutical": {"pharmaceutical", "dispensing"},
    "ventilation": {"ventilation", "support"},
    "nutritional": {"nutritional", "support"},
    "transfusion": {"transfusion"},
    "sterilisation": {"sterilisation"},
    "theatre": {"theatre"},
    "critical": {"critical", "care"},
}

def normalize_description(text: str):
    text = REF_CODE_RE.sub("", str(text))
    text = text.replace("-", " ").replace("/", " ")
    tokens = re.findall(r"[A-Za-z]+", text.lower())
    return [TOKEN_ALIASES.get(t, t) for t in tokens]

def word_score(token: str, word: str) -> float:
    token, word = token.lower(), word.lower()
    if token == word:
        return 1.0
    if len(token) >= 3 and word.startswith(token):
        return 0.85 + 0.15 * (len(token) / len(word))
    it = iter(word)
    if len(token) >= 2 and all(ch in it for ch in token):
        return 0.45 + 0.35 * (len(token) / len(word))
    r = difflib.SequenceMatcher(None, token, word).ratio()
    return r * 0.55 if r > 0.75 else 0.0

def score_candidate(desc_tokens, service_words):
    pairs = sorted(
        ((word_score(t, w), i, j) for i, t in enumerate(desc_tokens) for j, w in enumerate(service_words)),
        reverse=True,
    )
    used_i, used_j, matched_score, matched_pairs = set(), set(), 0.0, 0
    for s, i, j in pairs:
        if s <= 0 or i in used_i or j in used_j:
            continue
        used_i.add(i); used_j.add(j)
        matched_score += s
        matched_pairs += 1
    n_words, n_tokens = len(service_words), len(desc_tokens)
    coverage_desc = matched_pairs / n_tokens if n_tokens else 0
    return (matched_score / n_words) * (0.6 + 0.4 * coverage_desc) if n_words else 0

def anchor_sets(tokens):
    anchors = {t for t in tokens if t in CLINICAL_ANCHORS}
    classes = set()
    token_set = set(tokens)
    for key, aliases in SERVICE_CLASS_ALIASES.items():
        if token_set & aliases:
            classes.add(key)
    return anchors, classes

def candidate_conflict(desc_tokens, service_tokens):
    d_anchor, d_class = anchor_sets(desc_tokens)
    s_anchor, s_class = anchor_sets(service_tokens)
    anchor_conflict = bool(d_anchor and s_anchor and d_anchor.isdisjoint(s_anchor))
    class_conflict = bool(d_class and s_class and d_class.isdisjoint(s_class))
    return anchor_conflict, class_conflict, d_anchor, d_class, s_anchor, s_class

def match_description(desc: str, schedule: pd.DataFrame, top_k=8):
    tokens = normalize_description(desc)
    results = []
    for _, row in schedule.iterrows():
        svc = row["service"]
        svc_tokens = normalize_description(svc)
        score = score_candidate(tokens, svc_tokens)
        anchor_conflict, class_conflict, d_anchor, d_class, s_anchor, s_class = candidate_conflict(tokens, svc_tokens)
        if anchor_conflict:
            score -= 0.40
        if class_conflict:
            score -= 0.20
        results.append({
            "score": score, "service": svc,
            "anchor_conflict": anchor_conflict, "class_conflict": class_conflict,
            "d_anchor": d_anchor, "d_class": d_class, "s_anchor": s_anchor, "s_class": s_class,
        })
    results.sort(key=lambda r: (r["score"], r["service"]), reverse=True)
    return results[:top_k]

GAP_THRESHOLD = 0.08
MIN_SCORE = 0.55

def half_up(value):
    return int(Decimal(value).to_integral_value(rounding=ROUND_HALF_UP))

_base_rate_lookup = rate_schedule.set_index("service")["base_rate_cents"].to_dict()
_bundled_rate_lookup = {}
for _row in bundles.itertuples():
    _bundled_rate_lookup.setdefault(_row.service_a, set()).add(_row.bundled_rate_a_cents)
    _bundled_rate_lookup.setdefault(_row.service_b, set()).add(_row.bundled_rate_b_cents)

_plausible_cache = {}

def plausible_unit_prices(service):
    """Unit prices a line of this service could legitimately carry (secondary evidence only)."""
    if service in _plausible_cache:
        return _plausible_cache[service]

    starting_rates = {int(_base_rate_lookup[service])}
    starting_rates |= {int(r) for r in _bundled_rate_lookup.get(service, set())}

    premium_pcts = [int(p) for p in threshold_premiums.loc[
        threshold_premiums["service"] == service, "premium_percent"]] if len(threshold_premiums) else []
    weekend_pcts = [int(p) for p in weekend_uplifts.loc[
        weekend_uplifts["service"] == service, "weekend_uplift_percent"]] if len(weekend_uplifts) else []
    discount_pcts = [int(p) for p in volume_discounts.loc[
        volume_discounts["service"] == service, "discount_percent"]] if len(volume_discounts) else []

    prices = set()
    for start in starting_rates:
        uplifted = [start]
        uplifted += [half_up(Decimal(start) * (Decimal(100 + p) / 100)) for p in premium_pcts]
        uplifted += [half_up(Decimal(start) * (Decimal(100 + p) / 100)) for p in weekend_pcts]
        for rate in list(uplifted):
            prices.add(rate)
            for d in discount_pcts:
                prices.add(half_up(Decimal(rate) * (Decimal(100 - d) / 100)))

    _plausible_cache[service] = prices
    return prices


# ---- Resolve every distinct billing description against the Hospital 2 rate schedule ----
observed_prices = line_items.groupby("description")["unit_price_cents"].apply(lambda s: set(int(x) for x in s.unique()))

match_records = []
for desc in line_items["description"].dropna().astype(str).unique():
    top = match_description(desc, rate_schedule, top_k=8)
    top1, top2 = top[0], (top[1] if len(top) > 1 else None)
    gap = top1["score"] - (top2["score"] if top2 else 0.0)
    obs = observed_prices.get(desc, set())
    structurally_compatible = [r for r in top if not r["anchor_conflict"] and not r["class_conflict"]]

    status, chosen, reason = "needs_review", None, ""
    if (not top1["anchor_conflict"] and not top1["class_conflict"]
            and top1["score"] >= MIN_SCORE and gap >= GAP_THRESHOLD):
        status, chosen, reason = "matched", top1["service"], "strong_text_match"
    else:
        close = [r for r in structurally_compatible if r["score"] >= max(top1["score"] - GAP_THRESHOLD, 0)]
        consistent = [r for r in close if obs and obs.issubset(plausible_unit_prices(r["service"]))]
        if len(consistent) == 1 and consistent[0]["score"] >= 0.35:
            status, chosen, reason = "resolved_by_price", consistent[0]["service"], "secondary_price_support"
        else:
            if top1["anchor_conflict"]:
                reason = "clinical_anchor_conflict"
            elif top1["class_conflict"]:
                reason = "service_class_conflict"
            elif len(structurally_compatible) > 1:
                reason = "ambiguous_text_match"
            else:
                reason = "insufficient_text_evidence"

    match_records.append({
        "description": desc, "matched_service": chosen, "text_score": round(top1["score"], 3),
        "gap": round(gap, 3), "match_status": status, "match_reason": reason,
        "top_candidates": str([(round(r["score"], 3), r["service"]) for r in top[:3]]),
    })

description_matches = pd.DataFrame(match_records)

line_items = line_items.merge(
    description_matches[["description", "matched_service", "match_status", "match_reason"]],
    on="description", how="left", validate="many_to_one",
)
line_items["service_date_raw"] = line_items["service_date"]
line_items["service_date"] = pd.to_datetime(line_items["service_date_raw"], format="%Y-%m-%d", errors="coerce")
