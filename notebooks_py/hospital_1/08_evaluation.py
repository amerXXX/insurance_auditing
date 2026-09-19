# Hospital 1 pipeline, part 8/9 — depends on parts 1-7
# (uses invoice_summary, REPO_ROOT).
#
# Development-set evaluation — Hospital 1 only. Labels never feed back into the detector.
# This is the accuracy/methodology evidence for the shared audit method: precision/recall/F1,
# per-category detection performance, expected-total residuals, and confidence calibration.

hospital_1_labels = pd.read_csv(REPO_ROOT / "labels" / "hospital_1_labels.csv")
check = invoice_summary.merge(
    hospital_1_labels, on="invoice_id", how="left", suffixes=("", "_label")
)

tp = int(((check["flagged"] == 1) & (check["is_erroneous"] == 1)).sum())
fp = int(((check["flagged"] == 1) & (check["is_erroneous"] == 0)).sum())
fn = int(((check["flagged"] == 0) & (check["is_erroneous"] == 1)).sum())
tn = int(((check["flagged"] == 0) & (check["is_erroneous"] == 0)).sum())

accuracy = (tp + tn) / len(check)
precision = tp / (tp + fp) if tp + fp else 0.0
recall = tp / (tp + fn) if tp + fn else 0.0
f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

print(f"TP={tp}  FP={fp}  FN={fn}  TN={tn}")
print(f"accuracy={accuracy:.3f}  precision={precision:.3f}  recall={recall:.3f}  F1={f1:.3f}")

# Map internal category name to the label vocabulary where needed.
CATEGORY_MAP = {
    "unmatched_service_needs_review": "unknown_service",
    "unknown_service": "unknown_service",
    "exclusion_violation": "exclusion_window_violation",
    "weekend_uplift_omitted": "premium_omitted",
    "weekend_uplift_incorrectly_applied": "premium_incorrectly_applied",
}

def split_cats(value):
    if pd.isna(value) or not str(value).strip():
        return set()
    return {CATEGORY_MAP.get(x, x) for x in str(value).split("|")}

# Per-category detection recall/precision on the H1 dev labels.
label_categories = sorted({c for s in check["error_categories"] for c in split_cats(s)})
cat_rows = []
for cat in label_categories:
    label_pos = check["error_categories"].apply(lambda x: cat in split_cats(x))
    pred_pos = check["error_category"].apply(lambda x: cat in split_cats(x))
    tp_cat = int((label_pos & pred_pos).sum())
    fn_cat = int((label_pos & ~pred_pos).sum())
    fp_cat = int((~label_pos & pred_pos).sum())
    cat_rows.append({
        "category": cat,
        "label_invoices": int(label_pos.sum()),
        "detected": tp_cat,
        "missed": fn_cat,
        "category_recall": tp_cat / int(label_pos.sum()) if label_pos.sum() else 0.0,
        "category_precision": tp_cat / (tp_cat + fp_cat) if tp_cat + fp_cat else 0.0,
    })
category_metrics = pd.DataFrame(cat_rows).sort_values(["category_recall", "category"])
print("\nPer-category development performance:")
print(category_metrics.to_string(index=False))

# Expected total accuracy. Keep provisional rows visible instead of hiding them.
check["expected_total_exact"] = check["expected_total_cents"] == check["expected_total_cents_label"]
print(
    f"\nExact expected_total_cents match: {check['expected_total_exact'].mean():.1%} overall"
)
print(
    f"Exact expected_total_cents match on labelled-correct invoices: "
    f"{check.loc[check['is_erroneous'] == 0, 'expected_total_exact'].mean():.1%}"
)
print(
    f"Exact expected_total_cents match on labelled-erroneous invoices: "
    f"{check.loc[check['is_erroneous'] == 1, 'expected_total_exact'].mean():.1%}"
)

# Systematic residuals rather than a list of individual misses.
residuals = check[~check["expected_total_exact"]].copy()
if residuals.empty:
    print("\nNo labelled expected-total residuals remain.")
else:
    def residual_type(row):
        label = split_cats(row["error_categories"]); pred = split_cats(row["error_category"])
        if "daily_cap_exceeded" in label:
            return "daily-cap correction"
        if "duplicate_invoice_id" in label:
            return "duplicate-ID occurrence selection"
        if "exclusion_window_violation" in label:
            return "exclusion-window handling"
        if "unknown_service" in label:
            return "unknown-service provisional pricing"
        if "malformed_service_date" in label:
            return "malformed-date pricing"
        if "volume_discount" in label:
            return "volume-discount pricing"
        return "other contract-pricing residual"
    residuals["failure_type"] = residuals.apply(residual_type, axis=1)
    print("\nExpected-total residuals by failure type:")
    # Report the number of residual invoices and the magnitude of the discrepancy.
    # These are development-set diagnostics, not changes to the contract rules.
    residuals["abs_difference_cents"] = (
        residuals["expected_total_cents_label"] - residuals["expected_total_cents"]
    ).abs()
    print(
        residuals.groupby("failure_type").agg(
            invoices=("invoice_id", "count"),
            mean_abs_difference_cents=("abs_difference_cents", "mean"),
            total_abs_difference_cents=("abs_difference_cents", "sum"),
        ).reset_index().sort_values("invoices", ascending=False).to_string(index=False)
    )

# H1 calibration note for confidence: these are policy scores, not statistical probabilities.
check["prediction_correct"] = check["flagged"] == check["is_erroneous"]
print("\nMean stated confidence:")
print(check.groupby("prediction_correct")["confidence"].mean().rename(index={True: "correct", False: "incorrect"}))

# Confidence-bucket calibration check. With only 913 H1 invoices, treat these as descriptive
# development diagnostics rather than statistical calibration claims.
confidence_bins = pd.cut(
    check["confidence"],
    bins=[0, 0.5, 0.7, 0.85, 0.95, 1.000001],
    include_lowest=True,
)
confidence_metrics = check.assign(confidence_bucket=confidence_bins).groupby("confidence_bucket", observed=False).agg(
    invoices=("invoice_id", "count"),
    prediction_accuracy=("prediction_correct", "mean"),
    erroneous_invoices=("is_erroneous", "sum"),
).reset_index()
print("\nConfidence-bucket development check:")
print(confidence_metrics.to_string(index=False))

print("\nConfidence is heuristic audit certainty, not a calibrated probability of correctness.")
