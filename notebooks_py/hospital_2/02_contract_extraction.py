# Hospital 2 pipeline, part 2/7 — depends on 01_setup.py having run first
# (uses REPO_ROOT).

## Contract structure
#
# Hospital 2's agreement is prose, not tables. Each contracted Service gets one numbered
# clause of the form:
#
#   4.4 In respect of <Service>, the Provider shall invoice the Payer at the rate of
#       GBP 59.25 per hour. Where the Service Date of this Service does not fall on a
#       Business Day, the rate applicable to it shall be increased by twelve percent
#       (12%). <... several sentences of boilerplate ...>
#
# with any daily cap, threshold premium, non-business-day uplift, cumulative volume
# discount or bundle stated as further sentences inside the same clause, in words with
# the figure in brackets ("twenty-four (24)", "thirty percent (30%)"). The surrounding
# sentences are legal boilerplate that carries no pricing content and must be ignored.
#
# Mapping to the other hospitals' structure:
#
# | Hospital 2                        | Purpose                                  | H1 equiv | H5 equiv |
# |-----------------------------------|------------------------------------------|----------|----------|
# | Article III 3.2                   | (a)-(e) adjustment order                 | Sec. 3.2 | Sec. 3.1 |
# | Article III 3.1                   | half-up after each step                  | Sec. 3.1 | Sec. 3.2 |
# | clause in each service's Article  | base rate + unit basis                   | Sec. 4   | Table 1  |
# | "shall not bill more than N"      | daily cap per Patient per Service Day    | Sec. 8   | Table 1  |
# | "aggregate ... exceeds N"         | threshold premium                        | Sec. 5   | Sec. 5   |
# | "does not fall on a Business Day" | non-business-day uplift                  | Sec. 6   | Sec. 6   |
# | "billed as a bundle"              | same-day same-patient substitution       | Sec. 9   | Sec. 7   |
# | "cumulative utilisation exceeds"  | cumulative volume discount               | Sec. 7   | Sec. 8   |
# | Article XIII                      | invoicing rules                          | Sec. 11  | Sec. 10  |
#
# Two provision types present in the other contracts are genuinely ABSENT here, and their
# absence is load-bearing rather than an extraction failure (verified by searching the
# full text for every wording used elsewhere): Hospital 2 defines no exclusion windows,
# and it contains no prohibition on billing the same Service twice for the same Patient
# and Service Date. Clause 1.3 also removes both multipliers: a single facility (F-MAIN),
# "No facility differential applies", and rates apply "irrespective of the Patient's plan
# tier" -- so stages (b) and (c) of clause 3.2's order are the identity here.
#
# Every count extracted below is asserted against the number of times the corresponding
# phrase occurs in the raw text, so a clause the parser fails to recognise is a hard
# failure rather than a silently missing rule.

CONTRACT_NUMBER = "INS-H2-2024-1183"
CONTRACT_START = pd.Timestamp("2024-01-01")   # clause 1.2
CONTRACT_END = pd.Timestamp("2025-12-31")     # clause 1.2
FACILITY_CODE = "F-MAIN"                      # clause 1.3
SUBMISSION_WINDOW_DAYS = 60                   # clause 13.1

contract_path = REPO_ROOT / "contracts" / "hospital_2" / "master_services_agreement.md"
contract_text = contract_path.read_text(encoding="utf-8")

# One clause per contracted Service. The rate and unit basis are in the opening sentence.
SERVICE_RE = re.compile(
    r"^(?P<clause>\d+\.\d+)\s+In respect of (?P<service>.+?), the Provider shall invoice the Payer "
    r"at the rate of GBP (?P<rate>[\d,]+\.\d{2}) (?P<unit>per [a-z, ]+?)\.",
)
CAP_RE = re.compile(
    r"shall not bill more than [a-z\- ]+\((\d+)\) [a-z ]+ of this Service for a Patient "
    r"on a single Service Day"
)
PREMIUM_RE = re.compile(
    r"aggregate quantity of this Service delivered to a Patient on a single Service Day exceeds "
    r"[a-z\- ]+\((\d+)\) [a-z ]+, the rate applicable to that Service Day shall be increased by "
    r"[a-z\- ]+\((\d+)%\)"
)
WEEKEND_RE = re.compile(
    r"does not fall on a Business Day, the rate applicable to it shall be increased by "
    r"[a-z\- ]+\((\d+)%\)"
)
DISCOUNT_RE = re.compile(
    r"cumulative utilisation of this Service exceeds [a-z\- ]+\((\d+)\) [a-z ]+, counted "
    r"cumulatively across the whole term of this Agreement and aggregated across all Patients, "
    r"a discount of [a-z\- ]+\((\d+)%\) shall be applied to each subsequent Unit"
)
BUNDLE_RE = re.compile(
    r"Where this Service and (?P<other>.+?) are both delivered to the same Patient on the same "
    r"Service Day, the two shall be billed as a bundle, this Service at GBP (?P<rate_self>[\d,]+\.\d{2}) "
    r"per [a-z, ]+? and (?P=other) at GBP (?P<rate_other>[\d,]+\.\d{2}) per [a-z, ]+?, in substitution"
)


def gbp_to_cents(text):
    return int(Decimal(text.replace(",", "").strip()) * 100)


rate_rows, premium_rows, weekend_rows, discount_rows, bundle_rows = [], [], [], [], []

for line_number, line in enumerate(contract_text.splitlines(), start=1):
    line = line.strip()
    match = SERVICE_RE.match(line)
    if not match:
        continue
    service = match.group("service")
    cap = CAP_RE.search(line)
    rate_rows.append({
        "service": service,
        "contract_unit": match.group("unit"),
        "base_rate_cents": gbp_to_cents(match.group("rate")),
        "daily_cap": int(cap.group(1)) if cap else pd.NA,
        "contract_clause": match.group("clause"),
        "source_line": line_number,
    })
    for threshold, percent in PREMIUM_RE.findall(line):
        premium_rows.append({
            "service": service, "threshold_units": int(threshold),
            "premium_percent": int(percent),
            "contract_clause": match.group("clause"), "source_line": line_number,
        })
    for percent in WEEKEND_RE.findall(line):
        weekend_rows.append({
            "service": service, "weekend_uplift_percent": int(percent),
            "contract_clause": match.group("clause"), "source_line": line_number,
        })
    for threshold, percent in DISCOUNT_RE.findall(line):
        discount_rows.append({
            "service": service, "threshold_units": int(threshold),
            "discount_percent": int(percent),
            "contract_clause": match.group("clause"), "source_line": line_number,
        })
    for bundle in BUNDLE_RE.finditer(line):
        bundle_rows.append({
            "service_a": service, "bundled_rate_a_cents": gbp_to_cents(bundle.group("rate_self")),
            "service_b": bundle.group("other"), "bundled_rate_b_cents": gbp_to_cents(bundle.group("rate_other")),
            "contract_clause": match.group("clause"), "source_line": line_number,
        })

rate_schedule = pd.DataFrame(rate_rows)
threshold_premiums = pd.DataFrame(premium_rows)
weekend_uplifts = pd.DataFrame(weekend_rows)
volume_discounts = pd.DataFrame(discount_rows)

# Each bundle pair is described twice, once from each side's clause. Keep one row per
# unordered pair, oriented so service_a/service_b carry their own substituted rates.
_seen_pairs = set()
_deduped = []
for row in bundle_rows:
    key = frozenset((row["service_a"], row["service_b"]))
    if key in _seen_pairs:
        continue
    _seen_pairs.add(key)
    _deduped.append(row)
bundles = pd.DataFrame(_deduped)

# ---- Extraction completeness: every provision in the text must have been parsed ----
# A clause this parser does not recognise is a missing contract rule, which would show up
# downstream as an invoice silently priced without it. Fail loudly instead.
text_counts = {
    "services": len(re.findall(r"at the rate of GBP", contract_text)),
    "caps": len(re.findall(r"shall not bill more than", contract_text)),
    "premiums": len(re.findall(
        r"aggregate quantity of this Service delivered to a Patient on a single Service Day exceeds",
        contract_text)),
    "weekend": len(re.findall(r"does not fall on a Business Day", contract_text)),
    "discounts": len(re.findall(
        r"a discount of [a-z\- ]+\(\d+%\) shall be applied to each subsequent Unit", contract_text)),
    "bundle_sentences": len(re.findall(r"shall be billed as a bundle", contract_text)),
}
parsed_counts = {
    "services": len(rate_schedule),
    "caps": int(rate_schedule["daily_cap"].notna().sum()),
    "premiums": len(threshold_premiums),
    "weekend": len(weekend_uplifts),
    "discounts": len(volume_discounts),
    "bundle_sentences": len(bundle_rows),
}
for key, expected in text_counts.items():
    assert parsed_counts[key] == expected, (
        f"Hospital 2 extraction incomplete for {key}: parsed {parsed_counts[key]}, "
        f"text contains {expected}"
    )

assert rate_schedule["service"].is_unique
assert rate_schedule["base_rate_cents"].gt(0).all()
assert len(rate_schedule) == 76
assert len(bundles) == 3            # 6 bundle sentences describing 3 unordered pairs
assert set(bundles["service_b"]) <= set(rate_schedule["service"])

# Provisions the other hospitals have and this one genuinely does not. Asserting their
# absence keeps a future contract change from passing silently.
assert not re.search(r"shall not be billable|not billable within", contract_text), \
    "Hospital 2 was assumed to define no exclusion windows"
assert not re.search(r"twice for the same Patient|more than once", contract_text), \
    "Hospital 2 was assumed to contain no duplicate-billing prohibition"

print(f"Contract: {len(rate_schedule)} services, {parsed_counts['caps']} daily caps, "
      f"{len(threshold_premiums)} premiums, {len(weekend_uplifts)} weekend uplifts, "
      f"{len(volume_discounts)} discount tiers, {len(bundles)} bundle pairs "
      f"(all counts reconciled against the raw text)")
