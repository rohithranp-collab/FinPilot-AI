"""Financial What-If Simulation Service for FinPilot AI.

Allows users to simulate:
1. Large purchases (one-time or split with down payment)
2. Loan repayments (prepayment / accelerated EMI payoff)
3. Monthly EMI (new loan with principal, interest rate, and tenure)
4. Savings targets (goal amount within target months)
5. Additional recurring monthly expenses (rent upgrade, lifestyle, hiring)

Computes baseline vs simulated month-by-month balances, affordability metrics, and AI verdicts.
"""
import json
from datetime import date
from typing import Dict, Any, List
import numpy as np
from sqlalchemy.orm import Session

from app.models import Transaction, Simulation
from app.schemas import SimulationCreateRequest
from app.services.recommendations import generate_recommendations_and_budgets


def calculate_emi(principal: float, annual_rate_percent: float, tenure_months: int) -> float:
    """Calculate standard monthly amortizing EMI."""
    if tenure_months <= 0:
        return principal
    if annual_rate_percent <= 0:
        return round(principal / tenure_months, 2)
    r = (annual_rate_percent / 100.0) / 12.0
    factor = (1.0 + r) ** tenure_months
    emi = principal * r * factor / (factor - 1.0)
    return round(float(emi), 2)


def run_financial_simulation(
    db: Session, req: SimulationCreateRequest, save_to_db: bool = True
) -> Dict[str, Any]:
    """Execute a financial decision simulation against the user's real transaction baseline."""
    rec_overview = generate_recommendations_and_budgets(db)
    current_balance = float(rec_overview.get("current_balance", 0.0))
    monthly_income = float(rec_overview.get("monthly_income_estimate", 0.0))
    monthly_expense = float(rec_overview.get("monthly_expense_estimate", 0.0))
    baseline_monthly_surplus = round(monthly_income - monthly_expense, 2)

    horizon = max(int(req.duration_months), 1)
    total_amt = float(req.total_amount)
    rate = float(req.interest_rate)
    down_payment = float(req.down_payment or 0.0)
    start_offset = int(req.start_month_offset or 0)

    one_time_impact = 0.0
    monthly_impact = 0.0
    total_interest_cost = 0.0
    interest_saved = 0.0
    months_saved = 0
    scenario_summary = ""

    if req.scenario_type == "large_purchase":
        # One-time large purchase (or upfront cash outlay)
        one_time_impact = total_amt
        monthly_impact = 0.0
        scenario_summary = (
            f"One-time purchase of ₹{total_amt:,.0f} deducted in Month {start_offset + 1}."
        )

    elif req.scenario_type == "monthly_emi":
        # Financed via Down Payment + Monthly EMI over duration_months
        financed_principal = max(0.0, total_amt - down_payment)
        one_time_impact = down_payment
        monthly_impact = calculate_emi(financed_principal, rate, horizon)
        total_repayment = one_time_impact + (monthly_impact * horizon)
        total_interest_cost = round(max(0.0, total_repayment - total_amt), 2)
        scenario_summary = (
            f"Loan principal ₹{financed_principal:,.0f} at {rate:.1f}% p.a. for {horizon} months "
            f"→ Monthly EMI of ₹{monthly_impact:,.0f} (Total Interest: ₹{total_interest_cost:,.0f})."
        )

    elif req.scenario_type == "loan_repayment":
        # Prepaying / accelerating repayment of a loan of balance total_amt
        lump_sum = down_payment if down_payment > 0 else round(total_amt * 0.20, 2)
        extra_monthly = float(req.extra_monthly_payment or 0.0)
        base_emi = float(req.existing_emi) if req.existing_emi and req.existing_emi > 0 else calculate_emi(total_amt, max(rate, 9.0), horizon)

        one_time_impact = lump_sum
        monthly_impact = extra_monthly

        # Estimate interest saved from lump sum + extra monthly payment
        eff_rate_monthly = (max(rate, 9.0) / 100.0) / 12.0
        rem_principal_after_lump = max(0.0, total_amt - lump_sum)
        # Approximate standard remaining interest vs accelerated interest
        std_total_paid = base_emi * horizon
        std_interest = max(0.0, std_total_paid - total_amt)

        accel_emi = base_emi + extra_monthly
        if accel_emi > rem_principal_after_lump * eff_rate_monthly and eff_rate_monthly > 0:
            n_new = int(
                np.ceil(
                    -np.log(1.0 - (rem_principal_after_lump * eff_rate_monthly / accel_emi))
                    / np.log(1.0 + eff_rate_monthly)
                )
            )
            n_new = max(1, min(horizon, n_new))
        else:
            n_new = max(1, int(round(rem_principal_after_lump / max(accel_emi, 1.0))))

        accel_interest = max(0.0, (accel_emi * n_new) - rem_principal_after_lump)
        interest_saved = round(max(0.0, std_interest - accel_interest), 2)
        months_saved = max(0, horizon - n_new)
        scenario_summary = (
            f"Prepaying ₹{lump_sum:,.0f} upfront + ₹{extra_monthly:,.0f}/month extra on ₹{total_amt:,.0f} loan "
            f"saves ~₹{interest_saved:,.0f} in interest and shortens tenure by {months_saved} months."
        )

    elif req.scenario_type == "savings_target":
        # Setting aside money each month to reach a target of total_amt in horizon months
        net_goal = max(0.0, total_amt - down_payment)
        one_time_impact = down_payment
        # Account for optional return rate on savings/RD (e.g. 6.5% p.a. if interest_rate > 0)
        if rate > 0 and horizon > 1:
            r_m = (rate / 100.0) / 12.0
            monthly_impact = round(net_goal * r_m / (((1.0 + r_m) ** horizon) - 1.0), 2)
        else:
            monthly_impact = round(net_goal / horizon, 2)
        scenario_summary = (
            f"Accumulate ₹{total_amt:,.0f} in {horizon} months by allocating ₹{monthly_impact:,.0f}/month "
            + (f"(assuming {rate:.1f}% annual return)." if rate > 0 else "into dedicated savings.")
        )

    else:  # additional_expense
        # Recurring new monthly lifestyle/business expense of total_amt per month
        one_time_impact = down_payment
        monthly_impact = total_amt
        scenario_summary = (
            f"Recurring additional expense of ₹{monthly_impact:,.0f}/month over {horizon} months "
            f"(Total cumulative outflow: ₹{one_time_impact + monthly_impact * horizon:,.0f})."
        )

    # Generate month-by-month trajectory over the simulation horizon
    timeline: List[Dict[str, Any]] = []
    bal_before = current_balance
    bal_after = current_balance
    accumulated_savings_goal = down_payment if req.scenario_type == "savings_target" else 0.0
    min_balance_after = current_balance

    today = date.today()
    for m in range(1, horizon + 1):
        month_label = f"Month {m}"
        bal_before = round(bal_before + baseline_monthly_surplus, 2)

        m_outflow = 0.0
        if m == start_offset + 1:
            m_outflow += one_time_impact
        if m > start_offset:
            m_outflow += monthly_impact

        bal_after = round(bal_after + baseline_monthly_surplus - m_outflow, 2)
        min_balance_after = min(min_balance_after, bal_after)

        if req.scenario_type == "savings_target" and m > start_offset:
            r_m = (rate / 100.0) / 12.0 if rate > 0 else 0.0
            accumulated_savings_goal = round(
                accumulated_savings_goal * (1.0 + r_m) + monthly_impact, 2
            )

        timeline.append(
            {
                "month": m,
                "label": month_label,
                "baseline_balance": bal_before,
                "simulated_balance": bal_after,
                "monthly_decision_outflow": round(m_outflow, 2),
                "net_monthly_cashflow_after": round(baseline_monthly_surplus - m_outflow, 2),
                "goal_corpus": accumulated_savings_goal if req.scenario_type == "savings_target" else None,
            }
        )

    projected_before = timeline[-1]["baseline_balance"]
    projected_after = timeline[-1]["simulated_balance"]
    net_worth_delta = round(
        (projected_after + accumulated_savings_goal + interest_saved) - projected_before, 2
    )
    post_decision_monthly_surplus = round(baseline_monthly_surplus - monthly_impact, 2)

    # Evaluate Risk Level & Explainable Verdict
    emergency_buffer_1m = max(monthly_expense, 15000.0)
    if min_balance_after < 0:
        risk_level = "Critical"
        verdict = (
            f"HIGH RISK: This decision causes your projected account balance to turn negative "
            f"(minimum balance: ₹{min_balance_after:,.0f}). Your current monthly surplus of "
            f"₹{baseline_monthly_surplus:,.0f} and starting balance of ₹{current_balance:,.0f} cannot safely "
            f"absorb an upfront impact of ₹{one_time_impact:,.0f} plus ₹{monthly_impact:,.0f}/month. "
            "Recommendation: Delay this decision, reduce the amount, or opt for a longer tenure."
        )
    elif min_balance_after < emergency_buffer_1m or post_decision_monthly_surplus < 0:
        risk_level = "High"
        verdict = (
            f"CAUTION: While your balance stays positive (ending at ₹{projected_after:,.0f} vs baseline "
            f"₹{projected_before:,.0f}), your liquid reserve drops to ₹{min_balance_after:,.0f}—below a 1-month "
            f"expense safety buffer (₹{emergency_buffer_1m:,.0f})—and monthly surplus shrinks to "
            f"₹{post_decision_monthly_surplus:,.0f}/month."
        )
    elif post_decision_monthly_surplus < (monthly_income * 0.10):
        risk_level = "Moderate"
        verdict = (
            f"MODERATE IMPACT: Feasible, reducing your {horizon}-month ending balance from "
            f"₹{projected_before:,.0f} to ₹{projected_after:,.0f}. Post-decision monthly cash flow remains "
            f"positive at +₹{post_decision_monthly_surplus:,.0f}/month, though savings capacity is tighter."
        )
    else:
        risk_level = "Low"
        verdict = (
            f"AFFORDABLE & SAFE: Your finances comfortably support this scenario. After ₹{one_time_impact:,.0f} "
            f"initial outlay and ₹{monthly_impact:,.0f}/month impact, you retain a healthy monthly surplus of "
            f"+₹{post_decision_monthly_surplus:,.0f} and a {horizon}-month closing liquid balance of "
            f"₹{projected_after:,.0f}."
        )

    details_payload = {
        "scenario_summary": scenario_summary,
        "baseline_monthly_income": round(monthly_income, 2),
        "baseline_monthly_expense": round(monthly_expense, 2),
        "baseline_monthly_surplus": baseline_monthly_surplus,
        "post_decision_monthly_surplus": post_decision_monthly_surplus,
        "minimum_balance_reached": round(min_balance_after, 2),
        "total_interest_cost": total_interest_cost,
        "interest_saved": interest_saved,
        "months_saved": months_saved,
        "accumulated_savings_goal": round(accumulated_savings_goal, 2),
        "timeline": timeline,
    }

    sim_id = 0
    created_at_str = None
    if save_to_db:
        sim_row = Simulation(
            name=req.name.strip(),
            scenario_type=req.scenario_type,
            total_amount=round(total_amt, 2),
            monthly_impact=round(monthly_impact, 2),
            one_time_impact=round(one_time_impact, 2),
            duration_months=horizon,
            interest_rate=rate,
            current_balance_baseline=current_balance,
            projected_balance_before=projected_before,
            projected_balance_after=projected_after,
            net_worth_delta=net_worth_delta,
            risk_level=risk_level,
            verdict=verdict,
            parameters_json=json.dumps(details_payload),
            is_demo=False,
        )
        db.add(sim_row)
        db.commit()
        db.refresh(sim_row)
        sim_id = sim_row.id
        created_at_str = sim_row.created_at.isoformat() if sim_row.created_at else None

    return {
        "id": sim_id,
        "name": req.name.strip(),
        "scenario_type": req.scenario_type,
        "total_amount": round(total_amt, 2),
        "monthly_impact": round(monthly_impact, 2),
        "one_time_impact": round(one_time_impact, 2),
        "duration_months": horizon,
        "interest_rate": rate,
        "current_balance_baseline": current_balance,
        "projected_balance_before": projected_before,
        "projected_balance_after": projected_after,
        "net_worth_delta": net_worth_delta,
        "risk_level": risk_level,
        "verdict": verdict,
        "details": details_payload,
        "is_demo": False,
        "created_at": created_at_str,
    }


def list_saved_simulations(db: Session) -> List[Dict[str, Any]]:
    """Retrieve saved financial simulations ordered by most recent."""
    rows = db.query(Simulation).order_by(Simulation.created_at.desc(), Simulation.id.desc()).all()
    results = []
    for r in rows:
        try:
            details = json.loads(r.parameters_json) if r.parameters_json else {}
        except Exception:
            details = {}
        results.append(
            {
                "id": r.id,
                "name": r.name,
                "scenario_type": r.scenario_type,
                "total_amount": r.total_amount,
                "monthly_impact": r.monthly_impact,
                "one_time_impact": r.one_time_impact,
                "duration_months": r.duration_months,
                "interest_rate": r.interest_rate,
                "current_balance_baseline": r.current_balance_baseline,
                "projected_balance_before": r.projected_balance_before,
                "projected_balance_after": r.projected_balance_after,
                "net_worth_delta": r.net_worth_delta,
                "risk_level": r.risk_level,
                "verdict": r.verdict,
                "details": details,
                "is_demo": r.is_demo,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return results
