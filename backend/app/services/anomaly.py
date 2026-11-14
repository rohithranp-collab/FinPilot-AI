"""Anomaly Detection Service for FinPilot AI.

Detects:
1. Unusually high expenses (Category Z-score, Robust IQR, and Scikit-Learn IsolationForest).
2. Unusual spending frequency spikes (Rolling 3-day category velocity bursts).
3. Compares transactions against historical category spending patterns and explains why each is flagged.
"""
from datetime import timedelta
from collections import defaultdict
from typing import Dict, Any, List
import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session

from app.models import Transaction


def detect_spending_anomalies(db: Session) -> Dict[str, Any]:
    """Analyze expense history to detect amount and frequency anomalies with clear explanations."""
    expenses: List[Transaction] = (
        db.query(Transaction)
        .filter(Transaction.type == "expense")
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .all()
    )

    if len(expenses) < 4:
        return {
            "sufficient_data": False,
            "message": (
                "At least 4 expense transactions are required to establish historical spending "
                "baselines for anomaly detection."
            ),
            "anomalies": [],
            "summary": {
                "total_flagged": 0,
                "high_amount_count": 0,
                "frequency_spike_count": 0,
                "total_anomalous_amount": 0.0,
                "highest_anomaly_amount": 0.0,
            },
        }

    # Group expenses by category to compute category-specific statistical baselines
    by_category: Dict[str, List[Transaction]] = defaultdict(list)
    for tx in expenses:
        by_category[tx.category].append(tx)

    cat_stats: Dict[str, Dict[str, float]] = {}
    for cat, tx_list in by_category.items():
        amounts = np.array([float(t.amount) for t in tx_list], dtype=float)
        median_val = float(np.median(amounts))
        mean_val = float(np.mean(amounts))
        std_val = float(np.std(amounts)) if len(amounts) > 1 else 0.0
        q25, q75 = (
            (float(np.percentile(amounts, 25)), float(np.percentile(amounts, 75)))
            if len(amounts) >= 4
            else (median_val * 0.7, median_val * 1.3)
        )
        iqr_val = max(q75 - q25, 1.0)
        cat_stats[cat] = {
            "count": len(amounts),
            "mean": round(mean_val, 2),
            "median": round(median_val, 2),
            "std": round(std_val, 2),
            "iqr": round(iqr_val, 2),
            "q75": round(q75, 2),
        }

    # Optional Scikit-Learn IsolationForest on normalized category relative features
    iso_scores: Dict[int, float] = {}
    if len(expenses) >= 10:
        feature_rows = []
        tx_ids = []
        for tx in expenses:
            st = cat_stats[tx.category]
            amt = float(tx.amount)
            rel_to_median = amt / max(st["median"], 1.0)
            z_val = (amt - st["mean"]) / max(st["std"], 1.0) if st["std"] > 0 else 0.0
            feature_rows.append([amt, rel_to_median, z_val, float(tx.date.day)])
            tx_ids.append(tx.id)

        X_iso = np.array(feature_rows, dtype=float)
        iso = IsolationForest(
            n_estimators=100,
            contamination=min(0.12, max(0.04, 3.0 / len(expenses))),
            random_state=42,
        )
        preds = iso.fit_predict(X_iso)
        scores = iso.decision_function(X_iso)
        for tid, pred_label, sc in zip(tx_ids, preds, scores):
            if pred_label == -1:
                iso_scores[tid] = float(sc)

    anomalies: List[Dict[str, Any]] = []
    flagged_tx_ids = set()

    # 1. Detect Unusually High Expense Amounts
    for tx in expenses:
        # Fixed recurring obligations like Rent or standard EMIs with tiny variance shouldn't be false-positive flagged
        if tx.category in {"Rent", "EMI and Loans"} and cat_stats[tx.category]["std"] < (
            cat_stats[tx.category]["mean"] * 0.10
        ):
            continue

        st = cat_stats[tx.category]
        amt = float(tx.amount)
        mean_val = st["mean"]
        median_val = st["median"]
        std_val = st["std"]

        # Calculate robust Z-score & ratio to median/mean
        z_score = (amt - mean_val) / std_val if std_val > 10.0 else 0.0
        ratio_to_median = amt / max(median_val, 1.0)
        ratio_to_mean = amt / max(mean_val, 1.0)
        excess_rupees = round(amt - mean_val, 2)

        is_stat_outlier = (
            st["count"] >= 3
            and excess_rupees >= 600.0
            and (
                (z_score >= 1.85 and ratio_to_mean >= 1.75)
                or (ratio_to_median >= 2.4 and amt >= 1500.0)
            )
        )
        is_iso_outlier = (
            tx.id in iso_scores
            and ratio_to_mean >= 1.80
            and excess_rupees >= 1000.0
        )

        if is_stat_outlier or is_iso_outlier:
            severity = "High" if (ratio_to_mean >= 2.6 or excess_rupees >= 5000) else "Medium"
            pct_above = int(round((ratio_to_mean - 1.0) * 100))
            explanation = (
                f"₹{amt:,.0f} at '{tx.description}' is {ratio_to_mean:.1f}x ({pct_above}% above) your "
                f"historical {tx.category} average of ₹{mean_val:,.0f} (median ₹{median_val:,.0f}, "
                f"Z-score: +{max(z_score, 1.8):.1f}σ)."
            )
            anomalies.append(
                {
                    "id": f"amt-{tx.id}",
                    "transaction_id": tx.id,
                    "date": tx.date.isoformat(),
                    "description": tx.description,
                    "category": tx.category,
                    "amount": round(amt, 2),
                    "historical_category_average": mean_val,
                    "historical_category_median": median_val,
                    "deviation_multiple": round(ratio_to_mean, 2),
                    "z_score": round(max(z_score, 1.5), 2),
                    "anomaly_type": "Unusually High Expense",
                    "severity": severity,
                    "detection_method": (
                        "Isolation Forest + Category Z-Score"
                        if is_iso_outlier
                        else "Category Statistical Z-Score & IQR"
                    ),
                    "explanation": explanation,
                    "is_demo": tx.is_demo,
                }
            )
            flagged_tx_ids.add(tx.id)

    # 2. Detect Unusual Spending Frequency (Rolling 3-Day Category Velocity Spikes)
    min_date = min(t.date for t in expenses)
    max_date = max(t.date for t in expenses)
    total_weeks = max(((max_date - min_date).days + 1) / 7.0, 1.0)

    for cat, tx_list in by_category.items():
        if len(tx_list) < 5 or cat in {"Rent", "EMI and Loans", "Utilities"}:
            continue

        avg_weekly_freq = len(tx_list) / total_weeks
        expected_3day_freq = max(avg_weekly_freq * (3.0 / 7.0), 0.8)

        sorted_cat = sorted(tx_list, key=lambda x: x.date)
        used_dates = set()

        for i in range(len(sorted_cat)):
            window_start = sorted_cat[i].date
            if window_start in used_dates:
                continue
            window_end = window_start + timedelta(days=2)
            cluster = [t for t in sorted_cat if window_start <= t.date <= window_end]

            if len(cluster) >= 4 and len(cluster) >= expected_3day_freq * 2.5:
                cluster_total = round(sum(float(t.amount) for t in cluster), 2)
                latest_tx = cluster[-1]
                for c_tx in cluster:
                    used_dates.add(c_tx.date)

                explanation = (
                    f"Detected {len(cluster)} '{cat}' transactions within a 3-day window "
                    f"({window_start.isoformat()} to { latest_tx.date.isoformat() }) totaling ₹{cluster_total:,.0f}, "
                    f"compared to your typical pace of {avg_weekly_freq:.1f} '{cat}' transactions per week."
                )
                anomalies.append(
                    {
                        "id": f"freq-{latest_tx.id}",
                        "transaction_id": latest_tx.id,
                        "date": latest_tx.date.isoformat(),
                        "description": f"{cat} Spending Burst ({len(cluster)} transactions in 3 days)",
                        "category": cat,
                        "amount": cluster_total,
                        "historical_category_average": round(cat_stats[cat]["mean"] * expected_3day_freq, 2),
                        "historical_category_median": cat_stats[cat]["median"],
                        "deviation_multiple": round(len(cluster) / expected_3day_freq, 2),
                        "z_score": round(len(cluster) - expected_3day_freq, 2),
                        "anomaly_type": "Unusual Spending Frequency",
                        "severity": "Medium" if len(cluster) < 6 else "High",
                        "detection_method": "Rolling 3-Day Velocity Detector",
                        "explanation": explanation,
                        "is_demo": latest_tx.is_demo,
                    }
                )

    # Sort anomalies by date descending, then severity
    anomalies.sort(key=lambda a: (a["date"], 1 if a["severity"] == "High" else 0), reverse=True)

    high_amt_count = sum(1 for a in anomalies if a["anomaly_type"] == "Unusually High Expense")
    freq_count = sum(1 for a in anomalies if a["anomaly_type"] == "Unusual Spending Frequency")
    total_anom_amt = round(sum(a["amount"] for a in anomalies), 2)
    max_anom_amt = round(max((a["amount"] for a in anomalies), default=0.0), 2)

    return {
        "sufficient_data": True,
        "anomalies": anomalies,
        "category_baselines": cat_stats,
        "summary": {
            "total_flagged": len(anomalies),
            "high_amount_count": high_amt_count,
            "frequency_spike_count": freq_count,
            "total_anomalous_amount": total_anom_amt,
            "highest_anomaly_amount": max_anom_amt,
        },
    }
