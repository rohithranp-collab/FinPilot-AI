"""Analytics, Summary Statistics, Category Breakdown & Recurring Payment API Routes."""
from collections import defaultdict
from datetime import date
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Transaction
from app.services.recurring import detect_and_sync_recurring_payments
from app.services.recommendations import generate_recommendations_and_budgets
from app.services.anomaly import detect_spending_anomalies

router = APIRouter(tags=["Analytics & Recurring"])


def _ym(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _prev_ym(ym_str: str) -> str:
    y, m = map(int, ym_str.split("-"))
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


@router.get("/api/analytics", status_code=status.HTTP_200_OK)
def get_analytics_root(db: Session = Depends(get_db)):
    """Unified analytics endpoint returning summary KPIs, category breakdowns, and recurring payments."""
    summary_data = get_analytics_summary(db)
    categories_data = get_category_analytics(db)
    recurring_data = detect_and_sync_recurring_payments(db)
    return {
        **summary_data,
        "summary": summary_data,
        "categories": categories_data,
        "recurring": recurring_data,
    }


@router.get("/api/analytics/summary", status_code=status.HTTP_200_OK)
def get_analytics_summary(db: Session = Depends(get_db)):
    """Compute comprehensive financial summary, KPIs, MoM trends, and AI insights."""
    transactions: List[Transaction] = (
        db.query(Transaction).order_by(Transaction.date.asc(), Transaction.id.asc()).all()
    )

    if not transactions:
        return {
            "has_data": False,
            "total_balance": 0.0,
            "total_income": 0.0,
            "total_expenses": 0.0,
            "monthly_savings": 0.0,
            "savings_rate_percent": 0.0,
            "current_month": {
                "month": _ym(date.today()),
                "income": 0.0,
                "expenses": 0.0,
                "savings": 0.0,
                "income_mom_percent": 0.0,
                "expense_mom_percent": 0.0,
                "savings_mom_percent": 0.0,
            },
            "dataset_info": {
                "total_count": 0,
                "demo_count": 0,
                "user_count": 0,
                "is_demo_active": False,
            },
            "monthly_trends": [],
            "ai_insights": [
                {
                    "type": "info",
                    "category": "Getting Started",
                    "title": "No Transactions Stored Yet",
                    "message": "Add a transaction or click 'Seed Demo Data' to explore FinPilot AI analytics.",
                    "impact": "₹0",
                }
            ],
            "financial_health_score": 0,
            "health_label": "No Data",
        }

    total_income = round(sum(float(t.amount) for t in transactions if t.type == "income"), 2)
    total_expenses = round(sum(float(t.amount) for t in transactions if t.type == "expense"), 2)
    total_balance = round(total_income - total_expenses, 2)

    max_date = max(t.date for t in transactions)
    cur_ym = _ym(max_date)
    prev_ym = _prev_ym(cur_ym)

    monthly_inc: Dict[str, float] = defaultdict(float)
    monthly_exp: Dict[str, float] = defaultdict(float)
    demo_count = 0
    user_count = 0

    for t in transactions:
        ym = _ym(t.date)
        if t.type == "income":
            monthly_inc[ym] += float(t.amount)
        else:
            monthly_exp[ym] += float(t.amount)
        if t.is_demo:
            demo_count += 1
        else:
            user_count += 1

    cur_inc = round(monthly_inc.get(cur_ym, 0.0), 2)
    cur_exp = round(monthly_exp.get(cur_ym, 0.0), 2)
    cur_savings = round(cur_inc - cur_exp, 2)

    prev_inc = round(monthly_inc.get(prev_ym, 0.0), 2)
    prev_exp = round(monthly_exp.get(prev_ym, 0.0), 2)
    prev_savings = round(prev_inc - prev_exp, 2)

    # If current month has just started and has no income yet, also compute average monthly savings
    all_months = sorted(set(list(monthly_inc.keys()) + list(monthly_exp.keys())))
    monthly_trends = []
    running_cum_balance = 0.0
    for m_key in all_months:
        m_i = round(monthly_inc.get(m_key, 0.0), 2)
        m_e = round(monthly_exp.get(m_key, 0.0), 2)
        m_s = round(m_i - m_e, 2)
        running_cum_balance = round(running_cum_balance + m_s, 2)
        m_rate = round((m_s / m_i) * 100.0, 1) if m_i > 0 else 0.0
        monthly_trends.append(
            {
                "month": m_key,
                "income": m_i,
                "expenses": m_e,
                "savings": m_s,
                "cumulative_balance": running_cum_balance,
                "savings_rate_percent": m_rate,
            }
        )

    inc_mom = round(((cur_inc - prev_inc) / prev_inc) * 100.0, 1) if prev_inc > 0 else 0.0
    exp_mom = round(((cur_exp - prev_exp) / prev_exp) * 100.0, 1) if prev_exp > 0 else 0.0
    sav_mom = (
        round(((cur_savings - prev_savings) / abs(prev_savings)) * 100.0, 1)
        if prev_savings != 0
        else 0.0
    )

    savings_rate_overall = (
        round(((total_income - total_expenses) / total_income) * 100.0, 1)
        if total_income > 0
        else 0.0
    )

    rec_bundle = generate_recommendations_and_budgets(db)
    anom_bundle = detect_spending_anomalies(db)

    return {
        "has_data": True,
        "total_balance": total_balance,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "monthly_savings": cur_savings,
        "average_monthly_savings": rec_bundle.get("monthly_surplus_estimate", cur_savings),
        "savings_rate_percent": savings_rate_overall,
        "current_month": {
            "month": cur_ym,
            "previous_month": prev_ym,
            "income": cur_inc,
            "expenses": cur_exp,
            "savings": cur_savings,
            "previous_income": prev_inc,
            "previous_expenses": prev_exp,
            "previous_savings": prev_savings,
            "income_mom_percent": inc_mom,
            "expense_mom_percent": exp_mom,
            "savings_mom_percent": sav_mom,
        },
        "dataset_info": {
            "total_count": len(transactions),
            "demo_count": demo_count,
            "user_count": user_count,
            "is_demo_active": demo_count > 0,
        },
        "monthly_trends": monthly_trends,
        "ai_insights": rec_bundle.get("ai_insights", []),
        "financial_health_score": rec_bundle.get("financial_health_score", 0),
        "health_label": rec_bundle.get("health_label", "Fair"),
        "anomaly_count": anom_bundle["summary"]["total_flagged"],
    }


@router.get("/api/analytics/categories", status_code=status.HTTP_200_OK)
def get_category_analytics(db: Session = Depends(get_db)):
    """Return category-level expense and income breakdowns, percentages, and MoM comparisons."""
    transactions: List[Transaction] = (
        db.query(Transaction).order_by(Transaction.date.asc(), Transaction.id.asc()).all()
    )

    if not transactions:
        return {
            "expense_categories": [],
            "income_categories": [],
            "total_expenses": 0.0,
            "total_income": 0.0,
            "current_month": _ym(date.today()),
            "previous_month": _prev_ym(_ym(date.today())),
        }

    max_date = max(t.date for t in transactions)
    cur_ym = _ym(max_date)
    prev_ym = _prev_ym(cur_ym)

    exp_totals: Dict[str, float] = defaultdict(float)
    exp_counts: Dict[str, int] = defaultdict(int)
    exp_cur_month: Dict[str, float] = defaultdict(float)
    exp_prev_month: Dict[str, float] = defaultdict(float)

    inc_totals: Dict[str, float] = defaultdict(float)
    inc_counts: Dict[str, int] = defaultdict(int)

    for t in transactions:
        amt = float(t.amount)
        ym = _ym(t.date)
        if t.type == "expense":
            exp_totals[t.category] += amt
            exp_counts[t.category] += 1
            if ym == cur_ym:
                exp_cur_month[t.category] += amt
            elif ym == prev_ym:
                exp_prev_month[t.category] += amt
        else:
            inc_totals[t.category] += amt
            inc_counts[t.category] += 1

    grand_exp = sum(exp_totals.values())
    grand_inc = sum(inc_totals.values())

    expense_categories = []
    for cat, tot in sorted(exp_totals.items(), key=lambda x: x[1], reverse=True):
        c_m = round(exp_cur_month.get(cat, 0.0), 2)
        p_m = round(exp_prev_month.get(cat, 0.0), 2)
        mom_pct = round(((c_m - p_m) / p_m) * 100.0, 1) if p_m > 0 else (100.0 if c_m > 0 else 0.0)
        expense_categories.append(
            {
                "category": cat,
                "total_amount": round(tot, 2),
                "transaction_count": exp_counts[cat],
                "average_transaction": round(tot / max(exp_counts[cat], 1), 2),
                "percentage_of_expenses": round((tot / grand_exp) * 100.0, 1) if grand_exp > 0 else 0.0,
                "current_month_amount": c_m,
                "previous_month_amount": p_m,
                "mom_change_percent": mom_pct,
            }
        )

    income_categories = []
    for cat, tot in sorted(inc_totals.items(), key=lambda x: x[1], reverse=True):
        income_categories.append(
            {
                "category": cat,
                "total_amount": round(tot, 2),
                "transaction_count": inc_counts[cat],
                "percentage_of_income": round((tot / grand_inc) * 100.0, 1) if grand_inc > 0 else 0.0,
            }
        )

    return {
        "expense_categories": expense_categories,
        "income_categories": income_categories,
        "total_expenses": round(grand_exp, 2),
        "total_income": round(grand_inc, 2),
        "current_month": cur_ym,
        "previous_month": prev_ym,
    }


@router.get("/api/recurring", status_code=status.HTTP_200_OK)
def get_recurring_payments(db: Session = Depends(get_db)):
    """Detect and return recurring subscriptions, utility bills, regular income, and EMIs."""
    return detect_and_sync_recurring_payments(db)
