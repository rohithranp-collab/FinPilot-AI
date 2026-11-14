"""Indian Bank / UPI SMS Parser & Hinglish Voice Expense Parser for FinPilot AI.

Implements:
- Feature #2: WhatsApp & Indian Bank / UPI SMS Auto-Reader (HDFC, ICICI, SBI, Axis, Kotak, GPay/PhonePe/Paytm VPA)
- Feature #7: Voice Expense Entry with English + Hinglish Support ("Add 500 rupees for Swiggy yesterday", "Kal Uber mein 350 rupaye kharch kiye")
"""
import re
from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional

from app.services.categorization import categorize_transaction


BANK_PATTERNS = [
    ("HDFC Bank", r"\bhdfc\b"),
    ("ICICI Bank", r"\bicici\b"),
    ("State Bank of India (SBI)", r"\bsbi\b|\bstate bank\b"),
    ("Axis Bank", r"\baxis\b"),
    ("Kotak Mahindra Bank", r"\bkotak\b"),
    ("Yes Bank", r"\byes bank\b"),
    ("Paytm Payments Bank", r"\bpaytm\b"),
]

# Merchant extraction patterns common in Indian UPI & Bank SMS alerts
MERCHANT_PATTERNS = [
    # "to VPA swiggy@axisbank" or "to VPA zomato@hdfcbank"
    r"(?:to|from)\s+vpa\s+([a-zA-Z0-9._-]+)@[a-zA-Z0-9]+",
    # "at SWIGGY INDIA on" or "at AMAZON PAY on"
    r"\bat\s+([A-Za-z0-9 &._-]{2,35}?)(?:\s+on\b|\s+ref\b|\s+utr\b|\s+avl\b|\.|,|$)",
    # "to SWIGGY on" or "to UBER INDIA"
    r"\bto\s+([A-Za-z0-9 &._-]{2,35}?)(?:\s+on\b|\s+via\b|\s+ref\b|\s+upi\b|\.|,|$)",
    # "Info: UPI/123456/Swiggy" or "UPI-SWIGGY-"
    r"\bupi[/-](?:\d+[/-])?([A-Za-z0-9 &._-]{2,30}?)(?:[/-]|\s|$)",
    # "- Swiggy" at the end of SMS: "Rs. 500 debited from HDFC - Swiggy"
    r"-\s*([A-Za-z0-9 &._-]{2,30})\s*$",
    # "by NEFT-INFOSYS SALARY"
    r"\bby\s+(?:neft|imps|rtgs|ach)[-\s:]+([A-Za-z0-9 &._-]{2,35}?)(?:\s+on\b|\.|,|$)",
]


def _extract_amount(text: str) -> Optional[float]:
    """Extract rupee amount from Indian SMS or Hinglish voice command."""
    # Match patterns like: Rs. 1,250.50, INR 500, ₹2,400, 500 rupees, 350 rupaye, 1500 rs
    currency_patterns = [
        r"(?:rs\.?|inr|₹)\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
        r"([0-9][0-9,]*(?:\.\d{1,2})?)\s*(?:rupees|rupaye|rupaya|rs\.?|inr|₹)\b",
        r"\bfor\s+(?:rs\.?|inr|₹)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)\b",
        r"\bworth\s+(?:rs\.?|inr|₹)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)\b",
    ]
    for pat in currency_patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                val = float(raw)
                if val > 0:
                    return round(val, 2)
            except ValueError:
                continue

    # Fallback: standalone number that is not a 4-digit year or 6+ digit UPI ref
    for m in re.finditer(r"\b(\d{2,6}(?:\.\d{1,2})?)\b", text):
        raw = m.group(1)
        try:
            val = float(raw)
            if 10 <= val <= 500000 and not (1990 <= val <= 2035):
                return round(val, 2)
        except ValueError:
            continue
    return None


def _extract_sms_date(text: str) -> date:
    """Extract transaction date from SMS or default to today."""
    today = date.today()
    # Match DD-MM-YY or DD/MM/YYYY or DD-MMM-YY
    m_num = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b", text)
    if m_num:
        d, mo, y = int(m_num.group(1)), int(m_num.group(2)), int(m_num.group(3))
        if y < 100:
            y += 2000
        try:
            return date(y, mo, d)
        except ValueError:
            pass

    m_mon = re.search(
        r"\b(\d{1,2})[-\s](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-\s]?(\d{2,4})?\b",
        text,
        flags=re.IGNORECASE,
    )
    if m_mon:
        day_num = int(m_mon.group(1))
        mon_str = m_mon.group(2)[:3].title()
        yr_str = m_mon.group(3)
        yr_num = int(yr_str) if yr_str else today.year
        if yr_num < 100:
            yr_num += 2000
        try:
            dt = datetime.strptime(f"{day_num:02d}-{mon_str}-{yr_num:04d}", "%d-%b-%Y").date()
            return dt
        except ValueError:
            pass

    return today


def parse_indian_bank_sms(sms_text: str) -> Dict[str, Any]:
    """Parse an Indian Bank / UPI / WhatsApp forwarded alert into a structured transaction."""
    cleaned = (sms_text or "").strip()
    if not cleaned:
        raise ValueError("SMS text cannot be empty.")

    lower = cleaned.lower()

    # 1. Detect Credit (Income) vs Debit (Expense)
    credit_keywords = ("credited", "received", "deposited", "refund", "cashback", "cr to", "credit")
    debit_keywords = ("debited", "spent", "paid", "sent", "withdrawn", "dr from", "purchase", "charged")

    is_credit = any(k in lower for k in credit_keywords) and not any(
        k in lower for k in ("debited", "spent", "paid to")
    )
    tx_type = "income" if is_credit else "expense"

    # 2. Extract Amount
    amount = _extract_amount(cleaned)
    if amount is None:
        raise ValueError(
            "Could not detect an INR amount in the SMS. Include an amount like 'Rs. 500' or 'INR 1,250'."
        )

    # 3. Detect Bank & Payment Mode
    detected_bank = "Indian Bank / UPI"
    for bank_label, pat in BANK_PATTERNS:
        if re.search(pat, lower):
            detected_bank = bank_label
            break

    if "upi" in lower or "vpa" in lower:
        payment_method = "UPI / Bank"
    elif "card" in lower or "pos" in lower:
        payment_method = "Credit Card"
    elif any(k in lower for k in ("neft", "imps", "rtgs")):
        payment_method = "NEFT / RTGS"
    elif "ecs" in lower or "nach" in lower or "mandate" in lower:
        payment_method = "ECS Auto-Debit"
    else:
        payment_method = "UPI / Bank"

    # 4. Extract Merchant / Counterparty
    merchant = None
    for pat in MERCHANT_PATTERNS:
        m = re.search(pat, cleaned, flags=re.IGNORECASE)
        if m:
            candidate = m.group(1).strip(" -.,:/")
            # Clean VPA handles like swiggy.orders -> Swiggy Orders
            candidate = re.sub(r"[._-]+", " ", candidate).strip()
            if len(candidate) >= 2 and candidate.lower() not in ("a/c", "ac", "account", "bank", "upi"):
                merchant = candidate.title()
                break

    if not merchant:
        # Check known merchants directly in text
        known_merchants = [
            "Swiggy", "Zomato", "Uber", "Ola", "Rapido", "Amazon", "Flipkart", "Myntra",
            "BigBasket", "Blinkit", "Zepto", "DMart", "Netflix", "Spotify", "Hotstar",
            "JioFiber", "Airtel", "BESCOM", "Apollo Pharmacy", "PharmEasy", "HDFC Home Loan",
            "ICICI Auto Loan", "Bajaj Finserv", "Infosys", "TCS",
        ]
        for km in known_merchants:
            if km.lower() in lower:
                merchant = km
                break

    if not merchant:
        merchant = "UPI Merchant Transfer" if tx_type == "expense" else "Bank Credit / Inflow"

    # 5. Extract UPI Reference / Account Mask if present
    ref_match = re.search(r"(?:ref|utr|upi\s*ref|txn)[:\s#-]*(\d{6,14})", cleaned, flags=re.IGNORECASE)
    upi_ref = ref_match.group(1) if ref_match else None

    ac_match = re.search(r"(?:a/c|ac|acct|card)\s*(?:no\.?)?\s*[xX*]+(\d{3,4})", cleaned, flags=re.IGNORECASE)
    account_mask = f"XX{ac_match.group(1)}" if ac_match else None

    tx_date = _extract_sms_date(cleaned)
    cat_info = categorize_transaction(description=merchant, tx_type=tx_type, amount=amount)

    description = f"{merchant}"
    if detected_bank != "Indian Bank / UPI" and detected_bank.split()[0].lower() not in merchant.lower():
        description = f"{merchant} ({detected_bank.split()[0]})"

    return {
        "parsed": True,
        "date": tx_date.isoformat(),
        "amount": amount,
        "merchant": merchant,
        "description": description,
        "type": tx_type,
        "category": cat_info["category"],
        "categorization_reason": cat_info["reason"],
        "confidence": cat_info["confidence"],
        "payment_method": payment_method,
        "detected_bank": detected_bank,
        "account_mask": account_mask,
        "upi_reference": upi_ref,
        "raw_sms": cleaned,
    }


def parse_voice_command_hinglish(voice_text: str) -> Dict[str, Any]:
    """Parse an English or Hinglish spoken phrase into a structured transaction.

    Examples:
    - "Add 500 rupees for Swiggy yesterday"
    - "Kal Uber mein 350 rupaye kharch kiye"
    - "Aaj 1200 rupees Amazon shopping UPI se"
    - "Received 25000 freelance payment today"
    """
    cleaned = (voice_text or "").strip()
    if not cleaned:
        raise ValueError("Voice transcript cannot be empty.")

    lower = cleaned.lower()
    today = date.today()

    # 1. Relative date detection (English + Hinglish)
    if any(w in lower for w in ("day before yesterday", "parso", "parson")):
        tx_date = today - timedelta(days=2)
        date_label = "Day Before Yesterday (Parso)"
    elif any(w in lower for w in ("yesterday", "kal", "last night")):
        tx_date = today - timedelta(days=1)
        date_label = "Yesterday (Kal)"
    else:
        tx_date = _extract_sms_date(cleaned)
        date_label = "Today (Aaj)" if tx_date == today else tx_date.isoformat()

    # 2. Detect Income vs Expense (English + Hinglish)
    income_words = (
        "received", "got", "salary", "income", "credited", "mila", "mile",
        "aaya", "aaye", "kamaye", "freelance payment", "client payment",
    )
    tx_type = "income" if any(w in lower for w in income_words) else "expense"

    # 3. Extract Amount
    amount = _extract_amount(cleaned)
    if amount is None:
        raise ValueError(
            "Could not detect an amount in your voice command. Try saying e.g. 'Add 500 rupees for Swiggy yesterday'."
        )

    # 4. Clean filler words (English + Hinglish) to isolate merchant/description
    cleaned_desc = cleaned
    filler_patterns = [
        r"\b(?:add|spent|spend|paid|pay|for|on|at|in|to|from|received|got|worth)\b",
        r"\b(?:rupees|rupaye|rupaya|rs\.?|inr|₹)\b",
        r"\b(?:yesterday|today|kal|aaj|parso|parson|mein|me|pe|par|se|ka|ki|ke|kharch|kiye|kiya|diye|diya|mila|aaya)\b",
        r"\b\d+(?:,\d+)*(?:\.\d{1,2})?\b",
    ]
    for pat in filler_patterns:
        cleaned_desc = re.sub(pat, " ", cleaned_desc, flags=re.IGNORECASE)

    cleaned_desc = re.sub(r"\s+", " ", cleaned_desc).strip(" -.,?!")
    if len(cleaned_desc) < 2:
        cleaned_desc = "Voice Expense Entry" if tx_type == "expense" else "Voice Income Entry"
    else:
        cleaned_desc = cleaned_desc.title()

    cat_info = categorize_transaction(description=cleaned_desc, tx_type=tx_type, amount=amount)

    return {
        "parsed": True,
        "date": tx_date.isoformat(),
        "date_label": date_label,
        "amount": amount,
        "description": cleaned_desc,
        "type": tx_type,
        "category": cat_info["category"],
        "categorization_reason": cat_info["reason"],
        "confidence": cat_info["confidence"],
        "payment_method": "UPI / Bank",
        "raw_transcript": cleaned,
    }
