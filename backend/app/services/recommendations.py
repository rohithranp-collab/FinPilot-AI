"""AI Financial Recommendations, Personalized Category Budgets & Explainable Insights Service."""
from datetime import date, timedelta
from collections import defaultdict
from typing import Dict, Any, List
import numpy as np
from sqlalchemy.orm import Session

from app.models import Transaction, FinancialBudget
from app.services.recurring import detect_and_sync_recurring_payments
from app.services.forecasting import generate_cashflow_forecast


# Baseline target share of monthly income for expense categories (50/30/20 framework adapted for India)
INCOME_SHARE_BENCHMARKS: Dict[str, float] = {
    "Rent": 0.25,
    "EMI and Loans": 0.15,
    "Food": 0.12,
    "Shopping": 0.08,
    "Utilities": 0.06,
    "Transportation": 0.06,
    "Healthcare": 0.05,
    "Entertainment": 0.04,
    "Education": 0.05,
    "Other": 0.04,
}

DISCRETIONARY_CATEGORIES = {"Food", "Shopping", "Entertainment", "Other"}


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _previous_month_key(ym: str) -> str:
    year, month = map(int, ym.split("-"))
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def generate_recommendations_and_budgets(db: Session) -> Dict[str, Any]:
    """Calculate personalized category limits, saving opportunities, excessive spending alerts, and payment warnings."""
    transactions: List[Transaction] = (
        db.query(Transaction).order_by(Transaction.date.asc(), Transaction.id.asc()).all()
    )

    if not transactions:
        return {
            "sufficient_data": False,
            "financial_health_score": 0,
            "health_label": "No Data",
            "monthly_income_estimate": 0.0,
            "monthly_expense_estimate": 0.0,
            "potential_monthly_savings": 0.0,
            "category_budgets": [],
            "recommendations": [],
            "excessive_spending": [],
            "upcoming_payment_warnings": [],
            "ai_insights": [
                {
                    "type": "info",
                    "title": "Welcome to FinPilot AI",
                    "message": "Add your income and expense transactions or load Demo Data to unlock explainable AI insights.",
                    "impact": "₹0",
                }
            ],
        }

    max_date = max(t.date for t in transactions)
    min_date = min(t.date for t in transactions)
    current_ym = _month_key(max_date)
    prev_ym = _previous_month_key(current_ym)
    span_months = max(((max_date - min_date).days + 1) / 30.44, 1.0)

    # Monthly aggregations
    monthly_cat_exp: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    monthly_inc: Dict[str, float] = defaultdict(float)
    monthly_exp: Dict[str, float] = defaultdict(float)
    total_cat_exp: Dict[str, float] = defaultdict(float)

    total_income_all = 0.0
    total_expense_all = 0.0

    for t in transactions:
        ym = _month_key(t.date)
        amt = float(t.amount)
        if t.type == "income":
            monthly_inc[ym] += amt
            total_income_all += amt
        else:
            monthly_exp[ym] += amt
            monthly_cat_exp[ym][t.category] += amt
            total_cat_exp[t.category] += amt
            total_expense_all += amt

    current_balance = round(total_income_all - total_expense_all, 2)

    # Estimate typical monthly income & expense (using current month, previous month, and overall average)
    active_months = sorted(set(list(monthly_inc.keys()) + list(monthly_exp.keys())))
    if len(active_months) >= 2:
        # Use completed recent months or weighted average so partial current month doesn't skew downward
        recent_months = active_months[-min(3, len(active_months)) :]
        avg_monthly_inc = float(np.mean([monthly_inc[m] for m in recent_months if monthly_inc[m] > 0] or [total_income_all / span_months]))
        avg_monthly_exp = float(np.mean([monthly_exp[m] for m in recent_months if monthly_exp[m] > 0] or [total_expense_all / span_months]))
    else:
        avg_monthly_inc = max(monthly_inc.get(current_ym, 0.0), total_income_all / span_months)
        avg_monthly_exp = max(monthly_exp.get(current_ym, 0.0), total_expense_all / span_months)

    cur_month_inc = round(monthly_inc.get(current_ym, avg_monthly_inc), 2)
    cur_month_exp = round(monthly_exp.get(current_ym, 0.0), 2)
    prev_month_exp = round(monthly_exp.get(prev_ym, 0.0), 2)

    # 1. Calculate Personalized Category Budgets & Sync with FinancialBudget Table
    existing_budgets = {b.category: b for b in db.query(FinancialBudget).all()}
    category_budgets_list = []
    excessive_spending_list = []

    all_expense_categories = sorted(
        set(list(INCOME_SHARE_BENCHMARKS.keys()) + list(total_cat_exp.keys())),
        key=lambda c: total_cat_exp.get(c, 0.0),
        reverse=True,
    )

    for cat in all_expense_categories:
        if cat in {"Salary", "Freelance Income"}:
            continue

        cur_spent = round(monthly_cat_exp[current_ym].get(cat, 0.0), 2)
        prev_spent = round(monthly_cat_exp[prev_ym].get(cat, 0.0), 2)
        hist_monthly_avg = round(total_cat_exp.get(cat, 0.0) / span_months, 2)

        benchmark_share = INCOME_SHARE_BENCHMARKS.get(cat, 0.05)
        income_based_target = avg_monthly_inc * benchmark_share if avg_monthly_inc > 0 else hist_monthly_avg

        # Personalized AI Limit: blend historical habit (55%) with benchmark share (45%),
        # tightened by 12% for discretionary categories to encourage healthy savings
        if cat in {"Rent", "EMI and Loans"}:
            recommended_limit = round(max(cur_spent, prev_spent, hist_monthly_avg), -1)
        elif cat in DISCRETIONARY_CATEGORIES:
            blended = 0.55 * max(hist_monthly_avg, prev_spent) + 0.45 * income_based_target
            recommended_limit = round(max(blended * 0.88, 1000.0), -2)
        else:
            blended = 0.65 * max(hist_monthly_avg, prev_spent) + 0.35 * income_based_target
            recommended_limit = round(max(blended, 1000.0), -2)

        if recommended_limit <= 0 and cur_spent == 0 and prev_spent == 0:
            continue

        # Check if user customized budget
        db_budget = existing_budgets.get(cat)
        if db_budget and db_budget.is_custom:
            active_limit = round(float(db_budget.monthly_limit), 2)
        else:
            active_limit = max(recommended_limit, 500.0)

        mom_change_pct = (
            round(((cur_spent - prev_spent) / prev_spent) * 100.0, 1)
            if prev_spent > 0
            else (100.0 if cur_spent > 0 else 0.0)
        )
        utilization_pct = round((cur_spent / active_limit) * 100.0, 1) if active_limit > 0 else 0.0

        status = (
            "Exceeded"
            if cur_spent > active_limit
            else ("Warning" if utilization_pct >= 85.0 else "On Track")
        )

        budget_explanation = (
            f"Based on your average monthly {cat} spend of ₹{hist_monthly_avg:,.0f} "
            f"and {int(benchmark_share * 100)}% income benchmark (₹{income_based_target:,.0f}). "
            f"Current month ({current_ym}): ₹{cur_spent:,.0f} vs Previous month ({prev_ym}): ₹{prev_spent:,.0f}."
        )

        if db_budget:
            if not db_budget.is_custom:
                db_budget.monthly_limit = active_limit
            db_budget.recommended_limit = max(recommended_limit, 500.0)
            db_budget.current_spent = cur_spent
            db_budget.previous_month_spent = prev_spent
            db_budget.period_month = current_ym
            db_budget.explanation = budget_explanation
        else:
            db_budget = FinancialBudget(
                category=cat,
                monthly_limit=active_limit,
                recommended_limit=max(recommended_limit, 500.0),
                current_spent=cur_spent,
                previous_month_spent=prev_spent,
                period_month=current_ym,
                is_custom=False,
                explanation=budget_explanation,
            )
            db.add(db_budget)

        category_budgets_list.append(
            {
                "category": cat,
                "monthly_limit": active_limit,
                "recommended_limit": max(recommended_limit, 500.0),
                "current_spent": cur_spent,
                "previous_month_spent": prev_spent,
                "historical_monthly_avg": hist_monthly_avg,
                "utilization_percent": utilization_pct,
                "mom_change_percent": mom_change_pct,
                "remaining_budget": round(active_limit - cur_spent, 2),
                "status": status,
                "is_custom": bool(db_budget.is_custom),
                "explanation": budget_explanation,
            }
        )

        # Flag excessive spending
        if cur_spent > active_limit or (prev_spent > 500 and mom_change_pct >= 15.0 and cur_spent >= 1500):
            overage = max(0.0, round(cur_spent - active_limit, 2))
            delta_rupees = round(cur_spent - prev_spent, 2)
            excessive_spending_list.append(
                {
                    "category": cat,
                    "current_spent": cur_spent,
                    "previous_month_spent": prev_spent,
                    "budget_limit": active_limit,
                    "overage_amount": overage,
                    "mom_increase_percent": mom_change_pct,
                    "mom_increase_amount": delta_rupees,
                    "severity": "High" if (cur_spent > active_limit * 1.15 or mom_change_pct >= 25.0) else "Medium",
                    "explanation": (
                        f"Your {cat} spending in {current_ym} is ₹{cur_spent:,.0f}, which is "
                        + (
                            f"{mom_change_pct:+.1f}% (+₹{delta_rupees:,.0f}) higher than {prev_ym} (₹{prev_spent:,.0f})"
                            if delta_rupees > 0 and prev_spent > 0
                            else f"₹{overage:,.0f} above your recommended limit of ₹{active_limit:,.0f}"
                        )
                        + "."
                    ),
                }
            )

    db.commit()

    # 2. Recurring Payments & Upcoming Warnings
    rec_data = detect_and_sync_recurring_payments(db)
    rec_items = rec_data["recurring_payments"]
    rec_summary = rec_data["summary"]

    upcoming_warnings = []
    upcoming_14d_total = 0.0
    for r in rec_items:
        if r["type"] == "expense" and r["status"] == "Active" and -2 <= r["days_until_due"] <= 14:
            amt = float(r["average_amount"])
            upcoming_14d_total += amt
            due_str = (
                "Due Today"
                if r["days_until_due"] == 0
                else (
                    f"In {r['days_until_due']} days ({r['next_payment_date']})"
                    if r["days_until_due"] > 0
                    else f"Overdue by {abs(r['days_until_due'])} days ({r['next_payment_date']})"
                )
            )
            upcoming_warnings.append(
                {
                    "name": r["name"],
                    "category": r["category"],
                    "recurring_type": r["recurring_type"],
                    "amount": amt,
                    "next_payment_date": r["next_payment_date"],
                    "days_until_due": r["days_until_due"],
                    "urgency": "High" if r["days_until_due"] <= 3 else "Medium",
                    "warning_message": (
                        f"Upcoming {r['recurring_type']}: '{r['name']}' of ₹{amt:,.0f} is {due_str}. "
                        f"Ensure sufficient liquid balance (Current Balance: ₹{current_balance:,.0f})."
                    ),
                }
            )

    # 3. Generate Concrete, Data-Backed Saving Recommendations
    recommendations = []
    total_potential_savings = 0.0

    # Recommendation A: Discretionary category optimization
    for b in category_budgets_list:
        cat = b["category"]
        cur_s = b["current_spent"]
        prev_s = b["previous_month_spent"]
        ref_spend = max(cur_s, b["historical_monthly_avg"])

        if cat in DISCRETIONARY_CATEGORIES and ref_spend >= 2000:
            save_pct = 0.22 if cur_s > b["monthly_limit"] else 0.15
            save_amt = round((ref_spend * save_pct) / 50.0) * 50.0
            if save_amt >= 300:
                total_potential_savings += save_amt
                mom_clause = (
                    f"Your {cat.lower()} spending changed by {b['mom_change_percent']:+.1f}% compared with the previous month "
                    f"(₹{cur_s:,.0f} in {current_ym} vs ₹{prev_s:,.0f} in {prev_ym}). "
                    if prev_s > 0
                    else f"Your monthly {cat.lower()} spend averages ₹{ref_spend:,.0f}. "
                )
                recommendations.append(
                    {
                        "id": f"rec-save-{cat.lower()}",
                        "category": cat,
                        "type": "Saving Opportunity",
                        "priority": "High" if cur_s > b["monthly_limit"] else "Medium",
                        "title": f"Optimize {cat} Spending to Save ₹{save_amt:,.0f}/month",
                        "potential_monthly_savings": save_amt,
                        "annual_impact": round(save_amt * 12, 2),
                        "explanation": (
                            f"{mom_clause}By capping {cat} at ₹{max(ref_spend - save_amt, 1000):,.0f}/month "
                            f"(a {int(save_pct * 100)}% reduction), you can save ₹{save_amt:,.0f} every month "
                            f"(₹{save_amt * 12:,.0f}/year)."
                        ),
                        "action_steps": [
                            f"Set a weekly {cat} cap of ₹{round((ref_spend - save_amt) / 4.3, -1):,.0f}.",
                            f"Review top merchants in {cat} and eliminate impulse orders.",
                        ],
                    }
                )

    # Recommendation B: Subscription consolidation
    subs = [
        r for r in rec_items if r["recurring_type"] == "Subscription" and r["status"] == "Active"
    ]
    subs_total = rec_summary["subscriptions_total"]
    if subs_total > 0:
        sub_names = ", ".join(f"{s['name']} (₹{s['average_amount']:,.0f})" for s in subs[:4])
        sub_save = round(subs_total * 0.30, -1) if len(subs) >= 2 else 0.0
        total_potential_savings += sub_save
        recommendations.append(
            {
                "id": "rec-subscriptions",
                "category": "Entertainment",
                "type": "Subscription Audit",
                "priority": "Medium" if subs_total < 2500 else "High",
                "title": f"Audit {len(subs)} Active Subscriptions Totaling ₹{subs_total:,.0f}/month",
                "potential_monthly_savings": sub_save,
                "annual_impact": round(sub_save * 12, 2),
                "explanation": (
                    f"Your monthly subscription payments total ₹{subs_total:,.0f} across {len(subs)} services: "
                    f"{sub_names}. Rotating or pausing 1–2 underused plans can free up ₹{sub_save:,.0f}/month "
                    f"(₹{sub_save * 12:,.0f}/year)."
                ),
                "action_steps": [
                    "Rotate OTT streaming platforms instead of keeping all active simultaneously.",
                    "Switch essential annual memberships to yearly billing for 15–20% savings.",
                ],
            }
        )

    # Recommendation C: Debt / EMI-to-Income Ratio & Emergency Fund
    emi_total = rec_summary["emi_total"]
    if emi_total > 0 and avg_monthly_inc > 0:
        dti_pct = round((emi_total / avg_monthly_inc) * 100.0, 1)
        recommendations.append(
            {
                "id": "rec-emi-optimization",
                "category": "EMI and Loans",
                "type": "Debt Management",
                "priority": "High" if dti_pct >= 30.0 else "Low",
                "title": f"EMI-to-Income Ratio is {dti_pct}% (₹{emi_total:,.0f}/month)",
                "potential_monthly_savings": round(emi_total * 0.08, -1),
                "annual_impact": round(emi_total * 0.08 * 12, 2),
                "explanation": (
                    f"Your recurring EMI commitments total ₹{emi_total:,.0f}/month against an estimated monthly "
                    f"income of ₹{avg_monthly_inc:,.0f} ({dti_pct}% debt service ratio). "
                    + (
                        "Allocating 1 extra EMI prepayment per year reduces total loan interest by ~12–15%."
                        if dti_pct < 35.0
                        else "Your debt ratio exceeds the 30% prudent threshold; avoid taking new consumer EMIs."
                    )
                ),
                "action_steps": [
                    "Use the Financial Simulator tab to test a 5–10% lump-sum loan prepayment.",
                    "Prioritize highest interest rate debt first (Avalanche method).",
                ],
            }
        )

    # Recommendation D: Automated Savings / SIP Allocation
    monthly_surplus = round(avg_monthly_inc - avg_monthly_exp, 2)
    savings_rate_pct = round((monthly_surplus / avg_monthly_inc) * 100.0, 1) if avg_monthly_inc > 0 else 0.0
    target_savings = round(avg_monthly_inc * 0.25, -2)
    recommendations.append(
        {
            "id": "rec-savings-automation",
            "category": "Salary",
            "type": "Wealth & Buffer Strategy",
            "priority": "High" if savings_rate_pct < 20.0 else "Low",
            "title": (
                f"Boost Monthly Savings Rate from {savings_rate_pct:.1f}% toward 25% Target (₹{target_savings:,.0f})"
                if savings_rate_pct < 25.0
                else f"Maintain Strong {savings_rate_pct:.1f}% Savings Rate & Automate Surplus Deployment"
            ),
            "potential_monthly_savings": max(0.0, round(target_savings - max(monthly_surplus, 0.0), -2)),
            "annual_impact": round(max(monthly_surplus, target_savings) * 12, 2),
            "explanation": (
                f"Your average monthly income is ₹{avg_monthly_inc:,.0f} and average monthly expenses are "
                f"₹{avg_monthly_exp:,.0f}, leaving a net monthly cash surplus of ₹{monthly_surplus:,.0f} "
                f"({savings_rate_pct:.1f}% savings rate). Automating transfers right after salary credit "
                "prevents lifestyle creep."
            ),
            "action_steps": [
                f"Maintain an emergency liquidity buffer of 3 months' expenses (₹{round(avg_monthly_exp * 3, -3):,.0f}).",
                "Schedule an automated savings transfer on the 2nd of every month.",
            ],
        }
    )

    # 4. Build Explainable AI Insights (for Dashboard & Insights Feed)
    forecast_data = generate_cashflow_forecast(db, horizon_days=30)
    ai_insights = []

    # Insight 1: MoM Category Delta (e.g. Food / Shopping increase or decrease)
    for b in sorted(category_budgets_list, key=lambda x: abs(x["current_spent"] - x["previous_month_spent"]), reverse=True):
        if b["previous_month_spent"] > 0 and b["current_spent"] > 0:
            chg = b["mom_change_percent"]
            direction = "increased" if chg >= 0 else "decreased"
            ai_insights.append(
                {
                    "type": "warning" if chg > 12 else "positive",
                    "category": b["category"],
                    "title": f"{b['category']} Spending {direction.title()} by {abs(chg):.1f}%",
                    "message": (
                        f"Your {b['category'].lower()} spending {direction} by {abs(chg):.1f}% compared with "
                        f"the previous month (₹{b['current_spent']:,.0f} in {current_ym} vs "
                        f"₹{b['previous_month_spent']:,.0f} in {prev_ym})."
                    ),
                    "impact": f"{'+' if chg >= 0 else '-'}₹{abs(b['current_spent'] - b['previous_month_spent']):,.0f}/mo",
                }
            )
            break

    # Insight 2: Monthly Subscriptions Total
    if subs_total > 0:
        ai_insights.append(
            {
                "type": "info",
                "category": "Subscriptions",
                "title": f"Monthly Subscriptions Total ₹{subs_total:,.0f}",
                "message": (
                    f"Your monthly subscription payments total ₹{subs_total:,.0f} across {len(subs)} active "
                    f"services (₹{subs_total * 12:,.0f} annually)."
                ),
                "impact": f"₹{subs_total:,.0f}/mo",
            }
        )

    # Insight 3: Predicted Balance Warning or Surplus Projection
    neg_day = forecast_data.get("negative_balance_in_days")
    h30 = forecast_data["horizons"]["30_days"]
    if neg_day is not None:
        ai_insights.append(
            {
                "type": "danger",
                "category": "Cash Flow Forecast",
                "title": f"Negative Balance Risk in {neg_day} Days",
                "message": (
                    f"Your predicted balance may become negative in {neg_day} days based on scheduled bills "
                    "and recent spending velocity. Consider deferring non-essential purchases."
                ),
                "impact": f"₹{h30['predicted_balance']:,.0f} (30d)",
            }
        )
    else:
        ai_insights.append(
            {
                "type": "positive" if h30["predicted_net_flow"] >= 0 else "warning",
                "category": "Cash Flow Forecast",
                "title": "30-Day Cash Flow Trajectory",
                "message": (
                    f"Your 30-day predicted balance is ₹{h30['predicted_balance']:,.0f} "
                    f"(net 30-day flow: {'+' if h30['predicted_net_flow'] >= 0 else ''}₹{h30['predicted_net_flow']:,.0f}, "
                    f"confidence: {h30['confidence_percent']}%)."
                ),
                "impact": f"₹{h30['predicted_balance']:,.0f}",
            }
        )

    # Insight 4: Concrete Saving Opportunity
    top_save_rec = next((r for r in recommendations if r["type"] == "Saving Opportunity"), None)
    if top_save_rec:
        ai_insights.append(
            {
                "type": "positive",
                "category": top_save_rec["category"],
                "title": f"Save ₹{top_save_rec['potential_monthly_savings']:,.0f}/mo on {top_save_rec['category']}",
                "message": (
                    f"You can potentially save ₹{top_save_rec['potential_monthly_savings']:,.0f} per month "
                    f"by reducing {top_save_rec['category'].lower()} expenses toward your personalized AI budget."
                ),
                "impact": f"+₹{top_save_rec['potential_monthly_savings']:,.0f}/mo",
            }
        )

    # Calculate Overall Financial Health Score (0 - 100)
    savings_score = min(40.0, max(0.0, (savings_rate_pct / 25.0) * 40.0))
    budget_adherence_ratio = (
        sum(1 for b in category_budgets_list if b["status"] == "On Track")
        / max(len(category_budgets_list), 1)
    )
    budget_score = budget_adherence_ratio * 30.0
    liquidity_months = current_balance / max(avg_monthly_exp, 1.0)
    liquidity_score = min(30.0, max(0.0, (liquidity_months / 3.0) * 30.0))
    health_score = int(round(savings_score + budget_score + liquidity_score))
    health_label = (
        "Excellent"
        if health_score >= 80
        else ("Good" if health_score >= 65 else ("Fair" if health_score >= 45 else "Needs Attention"))
    )

    return {
        "sufficient_data": True,
        "reference_month": current_ym,
        "previous_month": prev_ym,
        "financial_health_score": health_score,
        "health_label": health_label,
        "current_balance": current_balance,
        "monthly_income_estimate": round(avg_monthly_inc, 2),
        "monthly_expense_estimate": round(avg_monthly_exp, 2),
        "monthly_surplus_estimate": monthly_surplus,
        "savings_rate_percent": savings_rate_pct,
        "potential_monthly_savings": round(total_potential_savings, 2),
        "category_budgets": category_budgets_list,
        "recommendations": recommendations,
        "excessive_spending": excessive_spending_list,
        "upcoming_payment_warnings": upcoming_warnings,
        "ai_insights": ai_insights,
    }
