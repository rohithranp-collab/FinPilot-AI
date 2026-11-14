"""Demo Data Seeding Utility for FinPilot AI.

Generates realistic Indian Rupee (₹) sample transactions, recurring payments,
historical predictions, and sample simulations across the past 105 days.
Clearly marks all demo records with `is_demo=True` so they are distinguished
from actual user-entered transactions (`is_demo=False`).
"""
from datetime import date, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, Base
from app.models import Transaction, RecurringPayment, FinancialBudget, Prediction, Simulation
from app.schemas import SimulationCreateRequest
from app.services.categorization import categorize_transaction
from app.services.recurring import detect_and_sync_recurring_payments
from app.services.forecasting import generate_cashflow_forecast, evaluate_prediction_accuracy
from app.services.recommendations import generate_recommendations_and_budgets
from app.services.simulation import run_financial_simulation


def _safe_month_date(year: int, month: int, day: int) -> date:
    """Return a valid date in (year, month) clamped to month end and today."""
    while month <= 0:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    for d in range(min(day, 28), 0, -1):
        try:
            return date(year, month, d)
        except ValueError:
            continue
    return date(year, month, 1)


def seed_demo_data(db: Session, reset_existing_demo: bool = True) -> Dict[str, Any]:
    """Seed realistic Indian financial demo data (`is_demo=True`) without touching user data."""
    if reset_existing_demo:
        db.query(Transaction).filter(Transaction.is_demo == True).delete()
        db.query(Prediction).filter(Prediction.is_demo == True).delete()
        db.query(Simulation).filter(Simulation.is_demo == True).delete()
        db.commit()

    today = date.today()
    cur_y, cur_m = today.year, today.month

    # Build 4 monthly buckets: M-3, M-2, M-1 (completed months) and M0 (current month up to today)
    months_info = []
    for offset in [3, 2, 1, 0]:
        y = cur_y
        m = cur_m - offset
        while m <= 0:
            m += 12
            y -= 1
        months_info.append((offset, y, m))

    raw_records: List[Dict[str, Any]] = []

    for offset, y, m in months_info:
        def d_clamp(preferred_day: int):
            if offset == 0 and preferred_day > today.day:
                return None
            return _safe_month_date(y, m, max(1, preferred_day))

        # 1. Monthly Recurring Salary & Freelance Income
        raw_records.append(
            {
                "date": d_clamp(1),
                "amount": 92000.0,
                "description": "Salary Credit - TechCorp India Pvt Ltd",
                "type": "income",
                "category": "Salary",
                "payment_method": "NEFT / Bank Transfer",
            }
        )
        raw_records.append(
            {
                "date": d_clamp(14),
                "amount": 18500.0 if offset != 1 else 22000.0,
                "description": "Upwork Freelance UI/UX Retainer Payout",
                "type": "income",
                "category": "Freelance Income",
                "payment_method": "Wire / UPI",
            }
        )

        # 2. Fixed Monthly Rent & EMIs
        raw_records.append(
            {
                "date": d_clamp(3),
                "amount": 22000.0,
                "description": "House Rent - Koramangala Apartment",
                "type": "expense",
                "category": "Rent",
                "payment_method": "UPI / Bank",
            }
        )
        raw_records.append(
            {
                "date": d_clamp(5),
                "amount": 11500.0,
                "description": "HDFC Car Loan EMI Auto-Debit",
                "type": "expense",
                "category": "EMI and Loans",
                "payment_method": "ECS Auto-Debit",
            }
        )
        raw_records.append(
            {
                "date": d_clamp(8),
                "amount": 3200.0,
                "description": "Bajaj Finserv Appliance EMI",
                "type": "expense",
                "category": "EMI and Loans",
                "payment_method": "ECS Auto-Debit",
            }
        )

        # 3. Monthly Subscriptions (staggered across the month so several are due in the next 1-10 days)
        raw_records.append(
            {
                "date": d_clamp(16),
                "amount": 649.0,
                "description": "Netflix Premium Monthly Subscription",
                "type": "expense",
                "category": "Entertainment",
                "payment_method": "Credit Card Mandate",
            }
        )
        raw_records.append(
            {
                "date": d_clamp(18),
                "amount": 179.0,
                "description": "Spotify Duo Music Subscription",
                "type": "expense",
                "category": "Entertainment",
                "payment_method": "UPI AutoPay",
            }
        )
        raw_records.append(
            {
                "date": d_clamp(20),
                "amount": 1499.0,
                "description": "Cult.fit Pro Gym Membership",
                "type": "expense",
                "category": "Healthcare",
                "payment_method": "Credit Card Mandate",
            }
        )
        raw_records.append(
            {
                "date": d_clamp(22),
                "amount": 1650.0,
                "description": "ChatGPT Plus AI Subscription",
                "type": "expense",
                "category": "Education",
                "payment_method": "Credit Card Mandate",
            }
        )

        # 4. Monthly Utilities
        elec_amounts = {3: 2050.0, 2: 2180.0, 1: 2120.0, 0: 2340.0}
        raw_records.append(
            {
                "date": d_clamp(17),
                "amount": elec_amounts[offset],
                "description": "BESCOM Electricity Bill Payment",
                "type": "expense",
                "category": "Utilities",
                "payment_method": "BBPS / UPI",
            }
        )
        raw_records.append(
            {
                "date": d_clamp(19),
                "amount": 1179.0,
                "description": "Airtel Xstream Fiber Broadband Bill",
                "type": "expense",
                "category": "Utilities",
                "payment_method": "UPI AutoPay",
            }
        )
        raw_records.append(
            {
                "date": d_clamp(24),
                "amount": 905.0,
                "description": "Indane LPG Gas Cylinder Refill",
                "type": "expense",
                "category": "Utilities",
                "payment_method": "UPI / Bank",
            }
        )

        def d_var(preferred_day: int) -> date:
            if offset == 0:
                mapped_day = max(1, min(today.day, int(round((preferred_day / 28.0) * max(today.day - 1, 1))) + 1))
                return _safe_month_date(y, m, mapped_day)
            return _safe_month_date(y, m, max(1, preferred_day))

        # 5. Discretionary Food & Grocery (Higher in current month to trigger +18~22% MoM insight)
        food_scale = 1.22 if offset == 0 else (1.0 if offset == 1 else 0.95)
        food_entries = [
            (2, round(1450 * food_scale, 0), "BigBasket Grocery Order"),
            (4, round(680 * food_scale, 0), "Swiggy Dinner Order - Meghana Foods"),
            (9, round(520 * food_scale, 0), "Zomato Lunch - Truffles Cafe"),
            (12, round(1820 * food_scale, 0), "DMart Supermarket Household & Groceries"),
            (16, round(460 * food_scale, 0), "Zepto Instant Grocery Delivery"),
            (19, round(790 * food_scale, 0), "Third Wave Coffee & Bakery"),
            (23, round(1120 * food_scale, 0), "Swiggy Instamart Weekly Essentials"),
            (26, round(890 * food_scale, 0), "Zomato Weekend Family Dining"),
        ]
        for day_num, amt, desc in food_entries:
            raw_records.append(
                {
                    "date": d_var(day_num),
                    "amount": amt,
                    "description": desc,
                    "type": "expense",
                    "category": "Food",
                    "payment_method": "UPI / Bank",
                }
            )

        # 6. Transportation
        transport_entries = [
            (3, 2200.0, "IndianOil Petrol Pump Fuel Refill"),
            (8, 440.0, "Uber Airport / Office Commute Cab"),
            (13, 350.0, "Namma Metro Smart Card Recharge"),
            (18, 2150.0, "Shell Petrol Station Fuel"),
            (22, 510.0, "Ola Prime Ride - Client Meeting"),
        ]
        for day_num, amt, desc in transport_entries:
            raw_records.append(
                {
                    "date": d_var(day_num),
                    "amount": amt,
                    "description": desc,
                    "type": "expense",
                    "category": "Transportation",
                    "payment_method": "UPI / Fastag",
                }
            )

        # 7. Shopping, Healthcare & Education
        shopping_entries = [
            (6, 2499.0 if offset > 0 else 3450.0, "Amazon India Home & Tech Accessories"),
            (14, 1899.0 if offset > 0 else 2890.0, "Myntra Apparel & Footwear Order"),
            (21, 1250.0, "Nykaa Personal Care & Grooming"),
        ]
        for day_num, amt, desc in shopping_entries:
            raw_records.append(
                {
                    "date": d_var(day_num),
                    "amount": amt,
                    "description": desc,
                    "type": "expense",
                    "category": "Shopping",
                    "payment_method": "Credit Card",
                }
            )

        raw_records.append(
            {
                "date": d_var(17),
                "amount": 850.0,
                "description": "Apollo Pharmacy Medicines & Vitamins",
                "type": "expense",
                "category": "Healthcare",
                "payment_method": "UPI / Bank",
            }
        )
        raw_records.append(
            {
                "date": d_var(20),
                "amount": 1299.0,
                "description": "Udemy Cloud Architecture & AI Course",
                "type": "expense",
                "category": "Education",
                "payment_method": "Credit Card",
            }
        )

    # 8. Add Realistic Anomalies in Recent Days (High Amount Outliers + 3-Day Frequency Burst)
    # Anomaly 1: High-value electronics shopping outlier (₹18,900 vs ~₹2,200 Shopping avg)
    raw_records.append(
        {
            "date": today - timedelta(days=3),
            "amount": 18900.0,
            "description": "Croma Electronics - Noise Cancelling Headphones & Monitor",
            "type": "expense",
            "category": "Shopping",
            "payment_method": "Credit Card",
        }
    )
    # Anomaly 2: Unusually high fine-dining bill (₹6,450 vs ~₹950 Food avg)
    raw_records.append(
        {
            "date": today - timedelta(days=6),
            "amount": 6450.0,
            "description": "Taj West End Fine Dining Celebration Dinner",
            "type": "expense",
            "category": "Food",
            "payment_method": "Credit Card",
        }
    )
    # Anomaly 3: 3-day Food order frequency burst (4 extra orders within 2 days)
    burst_day = today - timedelta(days=2)
    for b_desc, b_amt in [
        ("Swiggy Late Night Snacks Order", 640.0),
        ("Zomato Express Lunch Bowl", 580.0),
        ("Blinkit Gourmet Party Supplies", 1190.0),
        ("Starbucks Reserve Coffee & Croissant", 740.0),
    ]:
        raw_records.append(
            {
                "date": burst_day,
                "amount": b_amt,
                "description": b_desc,
                "type": "expense",
                "category": "Food",
                "payment_method": "UPI / Bank",
            }
        )

    # Insert all demo transactions with categorization explanations
    inserted_count = 0
    for item in raw_records:
        if item["date"] is None:
            continue
        cat_info = categorize_transaction(
            description=item["description"],
            tx_type=item["type"],
            amount=item["amount"],
            db=None,
        )
        tx = Transaction(
            date=item["date"],
            amount=item["amount"],
            description=item["description"],
            type=item["type"],
            category=item["category"] or str(cat_info["category"]),
            auto_categorized=True,
            categorization_reason=str(cat_info["reason"]),
            payment_method=item["payment_method"],
            is_demo=True,
        )
        db.add(tx)
        inserted_count += 1

    db.commit()

    # Sync recurring payments, budgets, forecasts, and backtest accuracy
    rec_res = detect_and_sync_recurring_payments(db)
    forecast_res = generate_cashflow_forecast(db, horizon_days=90)
    rec_budgets = generate_recommendations_and_budgets(db)
    acc_res = evaluate_prediction_accuracy(db)

    # Seed 2 sample simulations (`is_demo=True`)
    sim_samples = [
        SimulationCreateRequest(
            name="MacBook Pro M4 Workstation Purchase",
            scenario_type="monthly_emi",
            total_amount=165000.0,
            duration_months=12,
            interest_rate=11.5,
            down_payment=35000.0,
        ),
        SimulationCreateRequest(
            name="Emergency Corpus ₹3,00,000 Goal",
            scenario_type="savings_target",
            total_amount=300000.0,
            duration_months=10,
            interest_rate=7.0,
            down_payment=50000.0,
        ),
    ]
    for s_req in sim_samples:
        sim_out = run_financial_simulation(db, s_req, save_to_db=True)
        sim_row = db.query(Simulation).filter(Simulation.id == sim_out["id"]).first()
        if sim_row:
            sim_row.is_demo = True
    db.commit()

    return {
        "status": "success",
        "seeded_transactions": inserted_count,
        "detected_recurring_streams": len(rec_res["recurring_payments"]),
        "current_balance": forecast_res["current_balance"],
        "financial_health_score": rec_budgets["financial_health_score"],
        "prediction_accuracy_percent": (
            acc_res["metrics"]["accuracy_percent"] if acc_res.get("metrics") else None
        ),
    }


def clear_demo_data(db: Session) -> Dict[str, Any]:
    """Delete all demo records (`is_demo=True`) while keeping user-entered data (`is_demo=False`)."""
    deleted_tx = db.query(Transaction).filter(Transaction.is_demo == True).delete()
    deleted_pred = db.query(Prediction).filter(Prediction.is_demo == True).delete()
    deleted_sim = db.query(Simulation).filter(Simulation.is_demo == True).delete()
    db.commit()

    # Re-sync recurring and budgets for remaining user transactions
    detect_and_sync_recurring_payments(db)
    generate_recommendations_and_budgets(db)

    remaining_user_tx = db.query(Transaction).filter(Transaction.is_demo == False).count()
    return {
        "status": "cleared",
        "deleted_demo_transactions": deleted_tx,
        "deleted_demo_predictions": deleted_pred,
        "deleted_demo_simulations": deleted_sim,
        "remaining_user_transactions": remaining_user_tx,
    }


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        result = seed_demo_data(session, reset_existing_demo=True)
        print("FinPilot AI Demo Data Seeded Successfully:", result)
    finally:
        session.close()
