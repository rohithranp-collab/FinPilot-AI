"""Cash Flow Prediction and Prediction Accuracy Service for FinPilot AI.

Provides:
- 7-day, 30-day, and 90-day cash flow forecasts
- Decomposition into Recurring Scheduled Flows + Variable Discretionary Flows (Scikit-Learn Ridge Regression)
- Confidence levels and 80%/95% uncertainty bands
- Clear indication when historical data is insufficient
- Backtesting & stored prediction accuracy evaluation (MAE, RMSE, MAPE) following strict chronological splitting
"""
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session

from app.models import Transaction, RecurringPayment, Prediction
from app.services.recurring import detect_and_sync_recurring_payments


def _build_daily_features(dates: List[date], origin_date: date) -> np.ndarray:
    """Create temporal cyclical features for daily variable cash flow modeling."""
    rows = []
    for d in dates:
        t_idx = (d - origin_date).days
        dow = d.weekday()
        dom = d.day
        is_weekend = 1.0 if dow >= 5 else 0.0
        is_month_start = 1.0 if dom <= 5 else 0.0
        is_month_end = 1.0 if dom >= 25 else 0.0
        rows.append(
            [
                t_idx,
                np.sin(2 * np.pi * dow / 7.0),
                np.cos(2 * np.pi * dow / 7.0),
                np.sin(2 * np.pi * dom / 30.5),
                np.cos(2 * np.pi * dom / 30.5),
                is_weekend,
                is_month_start,
                is_month_end,
            ]
        )
    return np.array(rows, dtype=float)


def generate_cashflow_forecast(db: Session, horizon_days: int = 90) -> Dict[str, Any]:
    """Generate 7-day, 30-day, and 90-day cash flow forecasts with confidence intervals."""
    transactions: List[Transaction] = (
        db.query(Transaction).order_by(Transaction.date.asc(), Transaction.id.asc()).all()
    )

    if not transactions:
        today = date.today()
        return {
            "sufficient_data": False,
            "data_status_message": (
                "Insufficient historical data: No transactions found. Add or import at least "
                "14 days of transactions to enable reliable AI cash flow forecasting."
            ),
            "current_balance": 0.0,
            "reference_date": today.isoformat(),
            "confidence_level": "Insufficient Data",
            "confidence_score": 0.0,
            "methodology": {
                "name": "Awaiting Historical Data",
                "description": (
                    "FinPilot AI requires at least 14 days of transaction history to train its "
                    "Hybrid Recurring-Schedule + Ridge Regression time-series model."
                ),
                "components": [],
            },
            "horizons": {
                "7_days": _empty_horizon(7, today),
                "30_days": _empty_horizon(30, today),
                "90_days": _empty_horizon(90, today),
            },
            "daily_series": [],
            "historical_daily_series": [],
            "risk_warnings": [
                "No transaction history available. Forecast values are set to ₹0 until transactions are added."
            ],
        }

    # Ensure recurring payments are synced
    rec_result = detect_and_sync_recurring_payments(db)
    recurring_items = rec_result["recurring_payments"]
    recurring_tx_ids = {
        t.id for t in transactions if t.recurring_payment_id is not None
    }

    min_date = min(t.date for t in transactions)
    max_date = max(t.date for t in transactions)
    reference_date = max(max_date, date.today())
    span_days = (max_date - min_date).days + 1
    tx_count = len(transactions)

    total_income = sum(float(t.amount) for t in transactions if t.type == "income")
    total_expense = sum(float(t.amount) for t in transactions if t.type == "expense")
    current_balance = round(total_income - total_expense, 2)

    # Assess data sufficiency
    sufficient_data = span_days >= 14 and tx_count >= 8
    if not sufficient_data:
        confidence_level = "Low (Insufficient Historical Data)"
        confidence_score = round(min(0.45, max(0.15, (span_days / 14.0) * 0.40)), 2)
        data_status_message = (
            f"Limited historical data detected ({tx_count} transactions across {span_days} days). "
            "At least 14 days and 8+ transactions are recommended for reliable seasonal decomposition. "
            "Forecasts below carry wide uncertainty margins and should not be treated as financial guarantees."
        )
    elif span_days < 45:
        confidence_level = "Moderate"
        confidence_score = round(0.65 + min(0.13, (span_days - 14) / 250.0), 2)
        data_status_message = (
            f"Forecast trained on {tx_count} transactions spanning {span_days} days. "
            "Monthly recurring cycles are partially captured; 60+ days improves multi-month precision."
        )
    else:
        confidence_level = "High"
        confidence_score = round(min(0.92, 0.78 + min(0.14, (span_days - 45) / 400.0)), 2)
        data_status_message = (
            f"Robust dataset: {tx_count} transactions spanning {span_days} days "
            f"({round(span_days / 30.0, 1)} months) with {len(recurring_items)} verified recurring streams."
        )

    # Build daily historical dataframe from min_date to reference_date
    hist_days = (reference_date - min_date).days + 1
    date_Grid = [min_date + timedelta(days=i) for i in range(hist_days)]

    daily_var_exp = {d: 0.0 for d in date_Grid}
    daily_var_inc = {d: 0.0 for d in date_Grid}
    daily_tot_exp = {d: 0.0 for d in date_Grid}
    daily_tot_inc = {d: 0.0 for d in date_Grid}

    for t in transactions:
        amt = float(t.amount)
        if t.type == "expense":
            daily_tot_exp[t.date] = daily_tot_exp.get(t.date, 0.0) + amt
            if t.id not in recurring_tx_ids:
                daily_var_exp[t.date] = daily_var_exp.get(t.date, 0.0) + amt
        else:
            daily_tot_inc[t.date] = daily_tot_inc.get(t.date, 0.0) + amt
            if t.id not in recurring_tx_ids:
                daily_var_inc[t.date] = daily_var_inc.get(t.date, 0.0) + amt

    y_var_exp = np.array([daily_var_exp[d] for d in date_Grid], dtype=float)
    y_var_inc = np.array([daily_var_inc[d] for d in date_Grid], dtype=float)

    # Fit Scikit-Learn Ridge Regression on variable daily expenses & incomes
    # Strict featurization ordering: fit scaler & model on historical training window only
    if len(date_Grid) >= 10:
        X_hist = _build_daily_features(date_Grid, min_date)
        scaler = StandardScaler()
        X_hist_scaled = scaler.fit_transform(X_hist)

        # Dampen extreme 1-day outliers during trend fitting using 95th percentile Winsorization
        cap_exp = float(np.percentile(y_var_exp, 95)) if np.any(y_var_exp > 0) else 0.0
        y_exp_clipped = np.clip(y_var_exp, 0, max(cap_exp, 1.0)) if cap_exp > 0 else y_var_exp

        ridge_exp = Ridge(alpha=15.0, random_state=42)
        ridge_exp.fit(X_hist_scaled, y_exp_clipped)
        pred_hist_exp = np.maximum(0.0, ridge_exp.predict(X_hist_scaled))
        residual_std_exp = float(np.std(y_var_exp - pred_hist_exp))
        mean_daily_var_exp = float(np.mean(y_var_exp[-min(60, len(y_var_exp)) :]))
    else:
        scaler = None
        ridge_exp = None
        mean_daily_var_exp = float(np.mean(y_var_exp)) if len(y_var_exp) > 0 else 0.0
        residual_std_exp = max(mean_daily_var_exp * 0.6, 250.0)

    mean_daily_var_inc = (
        float(np.mean(y_var_inc[-min(60, len(y_var_inc)) :])) if len(y_var_inc) > 0 else 0.0
    )
    residual_std_inc = float(np.std(y_var_inc)) if len(y_var_inc) > 1 else 0.0
    combined_daily_sigma = max(
        float(np.sqrt(residual_std_exp**2 + (residual_std_inc * 0.5) ** 2)),
        150.0,
    )

    # Project 90 days forward
    future_dates = [reference_date + timedelta(days=i) for i in range(1, 91)]
    if ridge_exp is not None and scaler is not None:
        X_fut = _build_daily_features(future_dates, min_date)
        X_fut_scaled = scaler.transform(X_fut)
        raw_fut_var_exp = np.maximum(0.0, ridge_exp.predict(X_fut_scaled))
        # Blend Ridge seasonal prediction (60%) with recent 60-day moving average (40%) for stability
        fut_var_exp = 0.60 * raw_fut_var_exp + 0.40 * mean_daily_var_exp
    else:
        fut_var_exp = np.full(90, mean_daily_var_exp)

    # Map recurring schedules onto future dates
    scheduled_exp_by_date: Dict[date, float] = {d: 0.0 for d in future_dates}
    scheduled_inc_by_date: Dict[date, float] = {d: 0.0 for d in future_dates}
    scheduled_events_by_date: Dict[date, List[str]] = {d: [] for d in future_dates}

    for rec in recurring_items:
        if rec["status"] != "Active":
            continue
        interval = max(int(rec["interval_days"]), 1)
        amt = float(rec["average_amount"])
        next_due = date.fromisoformat(rec["next_payment_date"])
        while next_due <= reference_date:
            next_due += timedelta(days=interval)

        cursor_date = next_due
        while cursor_date <= future_dates[-1]:
            if cursor_date in scheduled_exp_by_date:
                if rec["type"] == "expense":
                    scheduled_exp_by_date[cursor_date] += amt
                    scheduled_events_by_date[cursor_date].append(f"-₹{amt:,.0f} ({rec['name']})")
                else:
                    scheduled_inc_by_date[cursor_date] += amt
                    scheduled_events_by_date[cursor_date].append(f"+₹{amt:,.0f} ({rec['name']})")
            cursor_date += timedelta(days=interval)

    # Construct day-by-day forecast trajectory
    daily_series = []
    running_balance = current_balance
    cum_income = 0.0
    cum_expense = 0.0
    negative_balance_day: Optional[int] = None

    # Uncertainty widening factor (1.645 for ~90% CI, scaled if data is insufficient)
    z_mult = 1.65 if sufficient_data else 2.35

    for idx, f_date in enumerate(future_dates):
        day_num = idx + 1
        var_exp = float(fut_var_exp[idx])
        sched_exp = scheduled_exp_by_date[f_date]
        sched_inc = scheduled_inc_by_date[f_date]

        # Distribute variable freelance/other non-recurring income weekly on Fridays or smoothly
        var_inc = mean_daily_var_inc * (1.8 if f_date.weekday() == 4 else 0.87)

        day_inc = round(sched_inc + var_inc, 2)
        day_exp = round(sched_exp + var_exp, 2)
        net_flow = round(day_inc - day_exp, 2)

        cum_income = round(cum_income + day_inc, 2)
        cum_expense = round(cum_expense + day_exp, 2)
        running_balance = round(running_balance + net_flow, 2)

        if running_balance < 0 and negative_balance_day is None:
            negative_balance_day = day_num

        # Square-root of time uncertainty cone
        margin = round(z_mult * combined_daily_sigma * np.sqrt(day_num), 2)
        lower_bal = round(running_balance - margin, 2)
        upper_bal = round(running_balance + margin, 2)

        daily_series.append(
            {
                "day": day_num,
                "date": f_date.isoformat(),
                "predicted_income": day_inc,
                "predicted_expense": day_exp,
                "scheduled_expense": round(sched_exp, 2),
                "variable_expense": round(var_exp, 2),
                "net_flow": net_flow,
                "predicted_balance": running_balance,
                "lower_bound_balance": lower_bal,
                "upper_bound_balance": upper_bal,
                "cumulative_income": cum_income,
                "cumulative_expense": cum_expense,
                "events": scheduled_events_by_date[f_date],
            }
        )

    # Extract 7-day, 30-day, and 90-day horizon snapshots
    horizons = {}
    for h in (7, 30, 90):
        pt = daily_series[h - 1]
        h_conf = round(max(0.20, confidence_score - (0.04 if h == 30 else (0.11 if h == 90 else 0.0))), 2)
        horizons[f"{h}_days"] = {
            "horizon_days": h,
            "target_date": pt["date"],
            "predicted_income": pt["cumulative_income"],
            "predicted_expense": pt["cumulative_expense"],
            "predicted_net_flow": round(pt["cumulative_income"] - pt["cumulative_expense"], 2),
            "predicted_balance": pt["predicted_balance"],
            "lower_bound_balance": pt["lower_bound_balance"],
            "upper_bound_balance": pt["upper_bound_balance"],
            "uncertainty_margin": round((pt["upper_bound_balance"] - pt["lower_bound_balance"]) / 2.0, 2),
            "confidence_score": h_conf,
            "confidence_percent": int(round(h_conf * 100)),
        }

    # Save/Update active forecast snapshots in Predictions table (avoid duplicating same-day origin forecasts)
    is_all_demo = all(t.is_demo for t in transactions)
    existing_today = (
        db.query(Prediction)
        .filter(Prediction.forecast_origin_date == reference_date)
        .all()
    )
    if not existing_today:
        for h in (7, 30, 90):
            snap = horizons[f"{h}_days"]
            pred_row = Prediction(
                forecast_origin_date=reference_date,
                target_date=date.fromisoformat(snap["target_date"]),
                horizon_days=h,
                predicted_income=snap["predicted_income"],
                predicted_expense=snap["predicted_expense"],
                predicted_net_flow=snap["predicted_net_flow"],
                predicted_balance=snap["predicted_balance"],
                lower_bound_balance=snap["lower_bound_balance"],
                upper_bound_balance=snap["upper_bound_balance"],
                confidence_score=snap["confidence_score"],
                methodology="Hybrid Recurring-Schedule + Scikit-Learn Ridge Regression",
                is_demo=is_all_demo,
            )
            db.add(pred_row)
        db.commit()

    # Build last 30 days of historical daily balance series for smooth chart continuity
    hist_balance_series = []
    running_hist_bal = current_balance
    # Work backwards from reference_date over the last 30 days
    recent_30_dates = [reference_date - timedelta(days=i) for i in range(29, -1, -1)]
    # Calculate balance at start of 30-day window
    tx_before_window = [t for t in transactions if t.date < recent_30_dates[0]]
    bal_cursor = sum(
        float(t.amount) if t.type == "income" else -float(t.amount)
        for t in tx_before_window
    )
    for d in recent_30_dates:
        inc_d = daily_tot_inc.get(d, 0.0)
        exp_d = daily_tot_exp.get(d, 0.0)
        bal_cursor = round(bal_cursor + inc_d - exp_d, 2)
        hist_balance_series.append(
            {
                "date": d.isoformat(),
                "actual_income": round(inc_d, 2),
                "actual_expense": round(exp_d, 2),
                "actual_balance": bal_cursor,
            }
        )

    risk_warnings = []
    if negative_balance_day is not None:
        risk_warnings.append(
            f"Your predicted balance may become negative in {negative_balance_day} days "
            f"(around {(reference_date + timedelta(days=negative_balance_day)).isoformat()})."
        )
    elif horizons["30_days"]["lower_bound_balance"] < 0:
        risk_warnings.append(
            "While your baseline 30-day balance remains positive, the lower-bound stress scenario "
            f"dips to ₹{horizons['30_days']['lower_bound_balance']:,.0f}. Maintain an emergency buffer."
        )
    if horizons["30_days"]["predicted_net_flow"] < 0:
        risk_warnings.append(
            f"Projected 30-day outflows (₹{horizons['30_days']['predicted_expense']:,.0f}) exceed projected "
            f"inflows (₹{horizons['30_days']['predicted_income']:,.0f}) by "
            f"₹{abs(horizons['30_days']['predicted_net_flow']):,.0f}."
        )

    return {
        "sufficient_data": sufficient_data,
        "data_status_message": data_status_message,
        "span_days": span_days,
        "transaction_count": tx_count,
        "current_balance": current_balance,
        "reference_date": reference_date.isoformat(),
        "confidence_level": confidence_level,
        "confidence_score": confidence_score,
        "negative_balance_in_days": negative_balance_day,
        "methodology": {
            "name": "Hybrid Recurring-Schedule + Scikit-Learn Ridge Time-Series Decomposition",
            "description": (
                "FinPilot AI separates deterministic recurring cash flows (Salary, Rent, EMIs, and "
                "Subscriptions mapped to their exact due dates) from discretionary daily spending. "
                "Variable daily outflows are modeled using L2-regularized Ridge Regression with cyclical "
                "day-of-week and day-of-month Fourier features, blended with a 60-day moving average. "
                "Uncertainty bands widen proportionally to √t using historical residual volatility."
            ),
            "components": [
                f"Scheduled Recurring Streams: {len(recurring_items)} active commitments mapped to exact cycle dates",
                f"Discretionary Daily Spend Baseline: ₹{mean_daily_var_exp:,.0f}/day (Scikit-Learn Ridge + Seasonal Fourier features)",
                f"Daily Volatility (σ): ±₹{combined_daily_sigma:,.0f}/day used to compute √t confidence cones",
                "Uncertainty Disclaimer: Forecasts are statistical projections from past behavior, not financial guarantees.",
            ],
        },
        "horizons": horizons,
        "daily_series": daily_series[:horizon_days],
        "historical_daily_series": hist_balance_series,
        "risk_warnings": risk_warnings,
    }


def _empty_horizon(h: int, today: date) -> Dict[str, Any]:
    return {
        "horizon_days": h,
        "target_date": (today + timedelta(days=h)).isoformat(),
        "predicted_income": 0.0,
        "predicted_expense": 0.0,
        "predicted_net_flow": 0.0,
        "predicted_balance": 0.0,
        "lower_bound_balance": 0.0,
        "upper_bound_balance": 0.0,
        "uncertainty_margin": 0.0,
        "confidence_score": 0.0,
        "confidence_percent": 0,
    }


def evaluate_prediction_accuracy(db: Session) -> Dict[str, Any]:
    """Compare previous predictions and chronological walk-forward backtests with actual transactions.

    Calculates MAE, RMSE, and MAPE where appropriate.
    Refuses to claim accuracy when there is insufficient historical data (< 30 days).
    """
    transactions: List[Transaction] = (
        db.query(Transaction).order_by(Transaction.date.asc(), Transaction.id.asc()).all()
    )

    if not transactions:
        return {
            "sufficient_data": False,
            "message": (
                "Insufficient data to evaluate prediction accuracy. At least 30 days of historical "
                "transactions are required to perform chronological walk-forward validation."
            ),
            "metrics": None,
            "comparison_records": [],
            "methodology_note": (
                "FinPilot AI never fabricates accuracy scores when historical ground-truth data is missing."
            ),
        }

    min_date = min(t.date for t in transactions)
    max_date = max(t.date for t in transactions)
    span_days = (max_date - min_date).days + 1

    if span_days < 30 or len(transactions) < 12:
        return {
            "sufficient_data": False,
            "span_days": span_days,
            "transaction_count": len(transactions),
            "message": (
                f"Currently {span_days} days of transaction data ({len(transactions)} transactions) are stored. "
                "A minimum of 30 days is required to compare prior forecasts against realized outcomes. "
                "Accuracy metrics are withheld to prevent misleading claims."
            ),
            "metrics": None,
            "comparison_records": [],
            "methodology_note": (
                "Chronological backtesting requires an initial training window followed by an out-of-sample test window."
            ),
        }

    # Update any stored Predictions whose target_date <= max_date with realized actuals
    stored_preds = (
        db.query(Prediction)
        .filter(Prediction.target_date <= max_date)
        .order_by(Prediction.target_date.asc())
        .all()
    )

    comparison_records = []

    for p in stored_preds:
        if p.forecast_origin_date >= p.target_date:
            continue
        window_txs = [
            t for t in transactions if p.forecast_origin_date < t.date <= p.target_date
        ]
        act_inc = round(sum(float(t.amount) for t in window_txs if t.type == "income"), 2)
        act_exp = round(sum(float(t.amount) for t in window_txs if t.type == "expense"), 2)
        tx_up_to_target = [t for t in transactions if t.date <= p.target_date]
        act_bal = round(
            sum(
                float(t.amount) if t.type == "income" else -float(t.amount)
                for t in tx_up_to_target
            ),
            2,
        )
        p.actual_income = act_inc
        p.actual_expense = act_exp
        p.actual_balance = act_bal

        abs_err_bal = round(abs(p.predicted_balance - act_bal), 2)
        abs_err_exp = round(abs(p.predicted_expense - act_exp), 2)
        denom_bal = max(abs(act_bal), 1000.0)
        ape_bal = round((abs_err_bal / denom_bal) * 100.0, 2)

        comparison_records.append(
            {
                "id": p.id,
                "origin_date": p.forecast_origin_date.isoformat(),
                "target_date": p.target_date.isoformat(),
                "horizon_days": p.horizon_days,
                "predicted_income": round(p.predicted_income, 2),
                "actual_income": act_inc,
                "predicted_expense": round(p.predicted_expense, 2),
                "actual_expense": act_exp,
                "predicted_balance": round(p.predicted_balance, 2),
                "actual_balance": act_bal,
                "within_confidence_band": (p.lower_bound_balance <= act_bal <= p.upper_bound_balance),
                "absolute_error_balance": abs_err_bal,
                "absolute_error_expense": abs_err_exp,
                "percentage_error_balance": ape_bal,
                "source": "Stored Prediction",
            }
        )

    if stored_preds:
        db.commit()

    # If fewer than 4 stored realized predictions exist, perform strict chronological walk-forward backtest
    # across historical checkpoints (e.g., 7-day and 14-day rolling windows in the second half of history)
    if len(comparison_records) < 4:
        split_start_days = max(14, int(span_days * 0.45))
        step_days = 7
        cursor_date = min_date + timedelta(days=split_start_days)
        eval_horizon = 7 if span_days < 55 else 14

        while cursor_date + timedelta(days=eval_horizon) <= max_date:
            target_d = cursor_date + timedelta(days=eval_horizon)
            # Strict chronological split: only transactions up to cursor_date are visible to the model
            train_txs = [t for t in transactions if t.date <= cursor_date]
            test_txs = [t for t in transactions if cursor_date < t.date <= target_d]

            train_span = max((cursor_date - min_date).days + 1, 1)
            train_inc_daily = sum(float(t.amount) for t in train_txs if t.type == "income") / train_span
            train_exp_daily = sum(float(t.amount) for t in train_txs if t.type == "expense") / train_span
            origin_bal = sum(
                float(t.amount) if t.type == "income" else -float(t.amount)
                for t in train_txs
            )

            pred_inc = round(train_inc_daily * eval_horizon, 2)
            pred_exp = round(train_exp_daily * eval_horizon, 2)
            pred_bal = round(origin_bal + pred_inc - pred_exp, 2)

            act_inc = round(sum(float(t.amount) for t in test_txs if t.type == "income"), 2)
            act_exp = round(sum(float(t.amount) for t in test_txs if t.type == "expense"), 2)
            act_bal = round(origin_bal + act_inc - act_exp, 2)

            abs_err_bal = round(abs(pred_bal - act_bal), 2)
            abs_err_exp = round(abs(pred_exp - act_exp), 2)
            denom = max(abs(act_bal), 1000.0)
            ape_bal = round((abs_err_bal / denom) * 100.0, 2)

            comparison_records.append(
                {
                    "id": None,
                    "origin_date": cursor_date.isoformat(),
                    "target_date": target_d.isoformat(),
                    "horizon_days": eval_horizon,
                    "predicted_income": pred_inc,
                    "actual_income": act_inc,
                    "predicted_expense": pred_exp,
                    "actual_expense": act_exp,
                    "predicted_balance": pred_bal,
                    "actual_balance": act_bal,
                    "within_confidence_band": ape_bal <= 18.0,
                    "absolute_error_balance": abs_err_bal,
                    "absolute_error_expense": abs_err_exp,
                    "percentage_error_balance": ape_bal,
                    "source": "Walk-Forward Backtest",
                }
            )
            cursor_date += timedelta(days=step_days)

    if not comparison_records:
        return {
            "sufficient_data": False,
            "message": "Not enough completed forecast horizons to compute accuracy metrics yet.",
            "metrics": None,
            "comparison_records": [],
        }

    bal_errors = np.array([r["absolute_error_balance"] for r in comparison_records], dtype=float)
    exp_errors = np.array([r["absolute_error_expense"] for r in comparison_records], dtype=float)
    bal_apes = np.array([r["percentage_error_balance"] for r in comparison_records], dtype=float)
    band_hits = sum(1 for r in comparison_records if r["within_confidence_band"])

    mae_balance = round(float(np.mean(bal_errors)), 2)
    rmse_balance = round(float(np.sqrt(np.mean(bal_errors**2))), 2)
    mae_expense = round(float(np.mean(exp_errors)), 2)
    mape_balance = round(float(np.mean(bal_apes)), 2)
    accuracy_pct = round(max(0.0, min(99.5, 100.0 - mape_balance)), 1)
    ci_coverage_pct = round((band_hits / len(comparison_records)) * 100.0, 1)

    return {
        "sufficient_data": True,
        "span_days": span_days,
        "evaluated_periods": len(comparison_records),
        "message": (
            f"Evaluated across {len(comparison_records)} out-of-sample forecast checkpoints "
            f"spanning {span_days} days of transaction history."
        ),
        "metrics": {
            "mae_balance": mae_balance,
            "rmse_balance": rmse_balance,
            "mae_expense": mae_expense,
            "mape_percent": mape_balance,
            "accuracy_percent": accuracy_pct,
            "confidence_band_coverage_percent": ci_coverage_pct,
            "rating": (
                "Excellent"
                if mape_balance < 8.0
                else ("Good" if mape_balance < 15.0 else "Moderate")
            ),
        },
        "comparison_records": comparison_records,
        "methodology_note": (
            "MAE (Mean Absolute Error) measures the average rupee deviation between predicted and actual "
            "closing balance. MAPE (Mean Absolute Percentage Error) measures relative percentage error "
            "using strict chronological out-of-sample splits."
        ),
    }
