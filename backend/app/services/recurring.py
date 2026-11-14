"""Recurring Payment Detection Service for FinPilot AI.

Detects:
- Monthly subscriptions (Netflix, Spotify, Youtube, Gym, SaaS, etc.)
- Recurring utility & rent bills (Rent, Broadband, Electricity, Mobile)
- Regular income (Salary, Monthly Retainers)
- EMI payments (Home loan, Car loan, Personal loan, Gadget EMI)
Estimates next payment date, interval frequency, and confidence score.
"""
import re
from datetime import date, timedelta
from collections import defaultdict
from typing import List, Dict, Any, Tuple
import numpy as np
from sqlalchemy.orm import Session

from app.models import Transaction, RecurringPayment


SUBSCRIPTION_KEYWORDS = {
    "netflix",
    "spotify",
    "youtube",
    "prime",
    "hotstar",
    "sonyliv",
    "apple",
    "icloud",
    "google one",
    "chatgpt",
    "claude",
    "github",
    "gym",
    "cult.fit",
    "membership",
    "subscription",
    "audible",
}

EMI_KEYWORDS = {
    "emi",
    "loan",
    "mortgage",
    "bajaj finserv",
    "hdfc loan",
    "icici loan",
    "sbi loan",
    "auto debit",
}

BILL_CATEGORIES = {"Rent", "Utilities"}


def normalize_merchant_name(description: str) -> str:
    """Normalize transaction description to cluster recurring merchants."""
    text = description.strip()
    # Remove trailing dates, invoice numbers, reference codes, month names
    text = re.sub(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|"
        r"january|february|march|april|june|july|august|september|october|november|december)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b(202\d|ref|txn|upi|neft|imps|ach|autopay|mandate|no|id|#)\b[\w\-:#]*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[\d#/_-]{3,}", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -–—:.,")
    return text.title() if text else description.strip().title()


def classify_recurring_type(name: str, category: str, tx_type: str) -> str:
    """Classify the recurring stream into Subscription, Recurring Bill, Regular Income, or EMI Payment."""
    lower_name = name.lower()
    if tx_type == "income":
        return "Regular Income"
    if category == "EMI and Loans" or any(k in lower_name for k in EMI_KEYWORDS):
        return "EMI Payment"
    if any(k in lower_name for k in SUBSCRIPTION_KEYWORDS) or category == "Entertainment":
        return "Subscription"
    if category in BILL_CATEGORIES:
        return "Recurring Bill"
    if category in {"Healthcare", "Education"} and any(
        w in lower_name for w in ("membership", "subscription", "plan", "fee", "tuition", "insurance", "gym", "cult")
    ):
        return "Subscription"
    # Exclude casual discretionary Food / Shopping / Transport from recurring bills unless explicitly marked
    if category in {"Food", "Shopping", "Transportation"} and not any(
        w in lower_name for w in ("subscription", "pass", "membership", "autopay", "plan", "monthly")
    ):
        return ""
    return "Recurring Bill"


def determine_frequency_label(avg_interval: float) -> Tuple[str, int]:
    """Map average interval in days to human-readable frequency and canonical days."""
    if 5 <= avg_interval <= 9:
        return "Weekly", 7
    if 12 <= avg_interval <= 17:
        return "Bi-Weekly", 14
    if 24 <= avg_interval <= 36:
        return "Monthly", 30
    if 55 <= avg_interval <= 66:
        return "Bi-Monthly", 60
    if 80 <= avg_interval <= 100:
        return "Quarterly", 90
    return "", 0


def detect_and_sync_recurring_payments(db: Session, reference_date: date = None) -> Dict[str, Any]:
    """Scan transaction history, detect recurring patterns, sync DB, and return detailed summary."""
    transactions: List[Transaction] = (
        db.query(Transaction).order_by(Transaction.date.asc(), Transaction.id.asc()).all()
    )

    if not transactions:
        db.query(RecurringPayment).delete()
        db.commit()
        return {
            "recurring_payments": [],
            "summary": {
                "total_monthly_recurring_expense": 0.0,
                "total_monthly_recurring_income": 0.0,
                "subscriptions_total": 0.0,
                "bills_total": 0.0,
                "emi_total": 0.0,
                "active_count": 0,
                "upcoming_7_days_count": 0,
            },
        }

    if reference_date is None:
        max_tx_date = max(t.date for t in transactions)
        reference_date = max(max_tx_date, date.today())

    groups: Dict[tuple, List[Transaction]] = defaultdict(list)
    for tx in transactions:
        norm_name = normalize_merchant_name(tx.description)
        key = (norm_name.lower(), tx.type, tx.category)
        groups[key].append(tx)

    detected_records: List[RecurringPayment] = []
    tx_to_recurring_map: List[tuple] = []

    # Clear existing recurring records and rebuild cleanly from actual transactions
    db.query(Transaction).update({Transaction.recurring_payment_id: None})
    db.query(RecurringPayment).delete()
    db.flush()

    for (norm_key, tx_type, category), tx_list in groups.items():
        # Deduplicate same-day identical entries or sort chronologically
        tx_list = sorted(tx_list, key=lambda x: x.date)
        if len(tx_list) < 2:
            continue

        # Compute intervals between consecutive dates
        dates = [t.date for t in tx_list]
        amounts = [float(t.amount) for t in tx_list]

        intervals = []
        for i in range(1, len(dates)):
            delta = (dates[i] - dates[i - 1]).days
            if delta > 0:
                intervals.append(delta)

        if not intervals:
            continue

        median_interval = float(np.median(intervals))
        std_interval = float(np.std(intervals)) if len(intervals) > 1 else 2.0

        freq_label, canonical_days = determine_frequency_label(median_interval)
        if not freq_label:
            continue

        # Check amount consistency (Coefficient of Variation)
        mean_amount = float(np.mean(amounts))
        std_amount = float(np.std(amounts))
        cv_amount = (std_amount / mean_amount) if mean_amount > 0 else 1.0

        # Allow higher variation for Utilities (electricity/water bills vary), stricter for Subscriptions/EMIs
        max_allowed_cv = 0.35 if category in {"Utilities", "Freelance Income"} else 0.20
        max_interval_std = 10.0 if canonical_days >= 28 else 4.0

        if cv_amount > max_allowed_cv or std_interval > max_interval_std:
            continue

        # Calculate confidence score (0.60 to 0.99)
        interval_regularity = max(0.0, 1.0 - (std_interval / max(canonical_days, 1)))
        amount_regularity = max(0.0, 1.0 - cv_amount)
        count_bonus = min(0.15, (len(tx_list) - 2) * 0.04)
        confidence = round(min(0.99, 0.50 * interval_regularity + 0.35 * amount_regularity + 0.15 + count_bonus), 2)

        display_name = normalize_merchant_name(tx_list[-1].description)
        rec_type = classify_recurring_type(display_name, category, tx_type)
        if not rec_type:
            continue
        last_date = dates[-1]

        # Estimate next payment date based on last payment date + canonical interval
        # If the next date is slightly in the past relative to reference_date but within 1 cycle, keep or roll forward
        next_date = last_date + timedelta(days=canonical_days)
        cycles_missed = 0
        while next_date < reference_date - timedelta(days=5) and cycles_missed < 3:
            next_date += timedelta(days=canonical_days)
            cycles_missed += 1

        status = "Active" if (reference_date - last_date).days <= (canonical_days * 2 + 10) else "Paused / Inactive"
        is_demo_flag = all(t.is_demo for t in tx_list)

        rec = RecurringPayment(
            name=display_name,
            category=category,
            type=tx_type,
            recurring_type=rec_type,
            average_amount=round(mean_amount, 2),
            frequency=freq_label,
            interval_days=canonical_days,
            last_payment_date=last_date,
            next_payment_date=next_date,
            confidence=confidence,
            occurrences=len(tx_list),
            status=status,
            is_demo=is_demo_flag,
        )
        db.add(rec)
        db.flush()

        for t in tx_list:
            t.recurring_payment_id = rec.id

        detected_records.append(rec)

    db.commit()

    # Format response and compute monthly normalized totals
    result_items = []
    monthly_expense_total = 0.0
    monthly_income_total = 0.0
    subscriptions_total = 0.0
    bills_total = 0.0
    emi_total = 0.0
    upcoming_7_days = 0

    # Sort by upcoming next_payment_date
    detected_records.sort(key=lambda r: r.next_payment_date)

    for r in detected_records:
        days_until = (r.next_payment_date - reference_date).days
        monthly_multiplier = 30.0 / max(r.interval_days, 1)
        monthly_equiv = round(r.average_amount * monthly_multiplier, 2)

        if r.status == "Active":
            if r.type == "expense":
                monthly_expense_total += monthly_equiv
                if r.recurring_type == "Subscription":
                    subscriptions_total += monthly_equiv
                elif r.recurring_type == "EMI Payment":
                    emi_total += monthly_equiv
                else:
                    bills_total += monthly_equiv
                if 0 <= days_until <= 7:
                    upcoming_7_days += 1
            else:
                monthly_income_total += monthly_equiv

        result_items.append(
            {
                "id": r.id,
                "name": r.name,
                "category": r.category,
                "type": r.type,
                "recurring_type": r.recurring_type,
                "average_amount": round(r.average_amount, 2),
                "monthly_equivalent": monthly_equiv,
                "frequency": r.frequency,
                "interval_days": r.interval_days,
                "last_payment_date": r.last_payment_date.isoformat(),
                "next_payment_date": r.next_payment_date.isoformat(),
                "days_until_due": days_until,
                "confidence": r.confidence,
                "occurrences": r.occurrences,
                "status": r.status,
                "is_demo": r.is_demo,
            }
        )

    return {
        "recurring_payments": result_items,
        "summary": {
            "total_monthly_recurring_expense": round(monthly_expense_total, 2),
            "total_monthly_recurring_income": round(monthly_income_total, 2),
            "subscriptions_total": round(subscriptions_total, 2),
            "bills_total": round(bills_total, 2),
            "emi_total": round(emi_total, 2),
            "active_count": sum(1 for r in detected_records if r.status == "Active"),
            "upcoming_7_days_count": upcoming_7_days,
        },
    }
