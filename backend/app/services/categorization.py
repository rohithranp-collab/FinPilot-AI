"""Explainable Rule-Based + Machine Learning Transaction Categorization Service.

Supports automatic categorization into:
- Food
- Shopping
- Transportation
- Healthcare
- Entertainment
- Education
- Rent
- Utilities
- EMI and Loans
- Salary
- Freelance Income
- Other
"""
import re
from typing import Tuple, List, Optional, Dict
from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from app.models import Transaction
from app.schemas import VALID_CATEGORIES


# Explainable Rule-Based Keyword Dictionary (Indian & Global Financial Context)
CATEGORY_RULES: Dict[str, Dict[str, List[str]]] = {
    "income": {
        "Salary": [
            "salary",
            "payroll",
            "stipend",
            "monthly pay",
            "bonus",
            "arrears",
            "employer",
            "infosys",
            "tcs",
            "wipro",
            "accenture",
            "tech corp",
            "neft salary",
            "paycheck",
            "reimbursement",
        ],
        "Freelance Income": [
            "freelance",
            "upwork",
            "fiverr",
            "toptal",
            "consulting",
            "client invoice",
            "project milestone",
            "retainer",
            "contract payment",
            "design project",
            "dev contract",
            "royalty",
            "youtube adsense",
            "stripe payout",
            "razorpay settlement",
            "dividend",
            "side hustle",
        ],
    },
    "expense": {
        "Food": [
            "swiggy",
            "zomato",
            "blinkit",
            "zepto",
            "bigbasket",
            "instamart",
            "dunzo",
            "dominos",
            "pizza",
            "kfc",
            "mcdonald",
            "starbucks",
            "third wave coffee",
            "blue tokai",
            "cafe",
            "restaurant",
            "dining",
            "biryani",
            "bakery",
            "grocery",
            "supermarket",
            "dmart",
            "reliance fresh",
            "nature basket",
            "food",
            "lunch",
            "dinner",
            "breakfast",
            "tea",
            "coffee",
            "haldiram",
            "barbeque",
        ],
        "Shopping": [
            "amazon",
            "flipkart",
            "myntra",
            "ajio",
            "nykaa",
            "meesho",
            "tatacliq",
            "croma",
            "reliance digital",
            "vijay sales",
            "zara",
            "h&m",
            "uniqlo",
            "westside",
            "pantaloons",
            "lifestyle",
            "decathlon",
            "ikea",
            "mall",
            "apparel",
            "clothing",
            "shoes",
            "electronics",
            "gadgets",
            "watch",
            "gift",
            "shopping",
        ],
        "Transportation": [
            "uber",
            "ola",
            "rapido",
            "namma yatri",
            "blu smart",
            "irctc",
            "metro",
            "bmrc",
            "dmrc",
            "local train",
            "redbus",
            "makemytrip",
            "goibibo",
            "indigo",
            "air india",
            "vistara",
            "akasa",
            "flight",
            "petrol",
            "diesel",
            "fuel",
            "indianoil",
            "hpcl",
            "bpcl",
            "shell",
            "fastag",
            "toll",
            "parking",
            "car service",
            "bike service",
            "cab",
            "auto",
        ],
        "Healthcare": [
            "apollo",
            "pharmeasy",
            "tata 1mg",
            "1mg",
            "netmeds",
            "medplus",
            "pharmacy",
            "medical",
            "medicine",
            "hospital",
            "fortis",
            "manipal",
            "max healthcare",
            "narayana",
            "clinic",
            "doctor",
            "consultation",
            "dental",
            "dentist",
            "eye care",
            "lenskart",
            "lab test",
            "diagnostics",
            "thyrocare",
            "dr lal",
            "health insurance",
            "star health",
            "cult.fit",
            "gym",
        ],
        "Entertainment": [
            "netflix",
            "spotify",
            "prime video",
            "hotstar",
            "jiocinema",
            "sonyliv",
            "zee5",
            "youtube premium",
            "apple music",
            "apple one",
            "bookmyshow",
            "pvr",
            "inox",
            "cinema",
            "movie",
            "concert",
            "steam",
            "playstation",
            "xbox",
            "gaming",
            "club",
            "bowling",
            "resort",
            "audible",
            "kindle",
        ],
        "Education": [
            "udemy",
            "coursera",
            "edx",
            "unacademy",
            "byjus",
            "physicswallah",
            "scaler",
            "upgrad",
            "pluralsight",
            "linkedin learning",
            "tuition",
            "school fee",
            "college fee",
            "university",
            "exam fee",
            "certification",
            "aws exam",
            "bookstore",
            "crossword",
            "course",
            "workshop",
            "coaching",
            "chatgpt plus",
            "claude pro",
            "github copilot",
        ],
        "Rent": [
            "house rent",
            "apartment rent",
            "flat rent",
            "pg rent",
            "hostel rent",
            "landlord",
            "nobroker",
            "nestaway",
            "stanza living",
            "rent transfer",
            "monthly rent",
            "office rent",
            "coworking",
            "wework",
            "awfis",
            "society maintenance",
            "maintenance charges",
            "rent",
        ],
        "Utilities": [
            "electricity",
            "power bill",
            "bescom",
            "mseb",
            "tata power",
            "adani electricity",
            "bses",
            "water bill",
            "bwssb",
            "jal board",
            "piped gas",
            "mahanagar gas",
            "igl",
            "indane",
            "hp gas",
            "bharatgas",
            "lpg cylinder",
            "airtel",
            "jio fiber",
            "jio recharge",
            "vi recharge",
            "bsnl",
            "act fibernet",
            "hathway",
            "broadband",
            "wifi",
            "internet bill",
            "mobile recharge",
            "postpaid bill",
            "dth",
            "tata play",
        ],
        "EMI and Loans": [
            "emi",
            "home loan",
            "car loan",
            "personal loan",
            "education loan",
            "bike loan",
            "bajaj finserv",
            "hdfc loan",
            "icici loan",
            "sbi loan",
            "axis loan",
            "kotak loan",
            "idfc first loan",
            "credit card emi",
            "simpl",
            "lazypay",
            "slice",
            "loan repayment",
            "mortgage",
            "auto debit emi",
        ],
    },
}


class CategorizationEngine:
    """Hybrid Rule-Based + Scikit-Learn ML Categorization Engine."""

    def __init__(self):
        self._ml_pipeline: Optional[Pipeline] = None
        self._trained_tx_count: int = 0

    @staticmethod
    def _preprocess_text(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^a-z0-9\s.&+-]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def _rule_based_match(
        self, description: str, tx_type: str
    ) -> Tuple[Optional[str], float, Optional[str]]:
        """Attempt deterministic keyword and pattern rule matching first."""
        clean_desc = self._preprocess_text(description)
        type_key = "income" if tx_type == "income" else "expense"

        rules_for_type = CATEGORY_RULES.get(type_key, {})

        # Prioritize longer / more specific phrase matches first
        best_match: Optional[Tuple[str, str, int]] = None
        for category, keywords in rules_for_type.items():
            for kw in keywords:
                pattern = r"(?:^|\b)" + re.escape(kw.lower()) + r"(?:\b|$)"
                if re.search(pattern, clean_desc) or kw.lower() in clean_desc:
                    kw_len = len(kw)
                    if best_match is None or kw_len > best_match[2]:
                        best_match = (category, kw, kw_len)

        if best_match:
            cat, matched_kw, _ = best_match
            confidence = 0.96 if len(matched_kw) >= 5 else 0.90
            reason = (
                f"Rule Engine: Matched keyword '{matched_kw}' for {type_key} "
                f"→ {cat} ({int(confidence * 100)}% confidence)"
            )
            return cat, confidence, reason

        # Check cross-type fallback if user entered e.g. refund or freelance
        for other_type, other_rules in CATEGORY_RULES.items():
            if other_type == type_key:
                continue
            for category, keywords in other_rules.items():
                for kw in keywords:
                    if kw.lower() in clean_desc:
                        return (
                            category,
                            0.82,
                            f"Rule Engine: Matched cross-category keyword '{kw}' → {category} (82% confidence)",
                        )

        return None, 0.0, None

    def _train_or_predict_ml(
        self, description: str, tx_type: str, db: Optional[Session] = None
    ) -> Tuple[Optional[str], float, Optional[str]]:
        """Train TF-IDF + LogisticRegression classifier on stored history for unknown descriptions."""
        if db is None:
            return None, 0.0, None

        try:
            history = (
                db.query(Transaction.description, Transaction.category)
                .filter(
                    Transaction.type == tx_type,
                    Transaction.category != "Other",
                )
                .all()
            )
            if len(history) < 12:
                return None, 0.0, None

            texts = [self._preprocess_text(row[0]) for row in history]
            labels = [row[1] for row in history]
            unique_labels = set(labels)
            if len(unique_labels) < 2:
                return None, 0.0, None

            # Train lightweight TF-IDF + LogisticRegression model
            pipeline = Pipeline(
                [
                    (
                        "tfidf",
                        TfidfVectorizer(
                            ngram_range=(1, 2),
                            min_df=1,
                            sublinear_tf=True,
                        ),
                    ),
                    (
                        "clf",
                        LogisticRegression(
                            C=2.0,
                            max_iter=300,
                            random_state=42,
                        ),
                    ),
                ]
            )
            pipeline.fit(texts, labels)
            clean_query = self._preprocess_text(description)
            probs = pipeline.predict_proba([clean_query])[0]
            classes = pipeline.classes_
            max_idx = int(probs.argmax())
            best_prob = float(probs[max_idx])
            predicted_cat = str(classes[max_idx])

            if best_prob >= 0.42:
                reason = (
                    f"ML Classifier (TF-IDF + Logistic Regression): Learned from {len(history)} "
                    f"historical transactions → {predicted_cat} ({int(best_prob * 100)}% confidence)"
                )
                return predicted_cat, round(best_prob, 2), reason
        except Exception:
            return None, 0.0, None

        return None, 0.0, None

    def categorize(
        self,
        description: str,
        tx_type: str = "expense",
        amount: Optional[float] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, object]:
        """Categorize a transaction and explain the decision."""
        # Step 1: Rule-based matching
        cat, conf, reason = self._rule_based_match(description, tx_type)
        if cat:
            return {
                "category": cat,
                "confidence": conf,
                "method": "Rule-Based Engine",
                "reason": reason,
            }

        # Step 2: ML Classifier on historical transactions
        ml_cat, ml_conf, ml_reason = self._train_or_predict_ml(description, tx_type, db)
        if ml_cat:
            return {
                "category": ml_cat,
                "confidence": ml_conf,
                "method": "ML Classifier",
                "reason": ml_reason,
            }

        # Step 3: Heuristic fallback based on transaction type & amount
        if tx_type == "income":
            if amount and amount >= 25000:
                return {
                    "category": "Salary",
                    "confidence": 0.60,
                    "method": "Amount Heuristic",
                    "reason": "Heuristic: High-value credit (≥ ₹25,000) defaulted to Salary (60% confidence)",
                }
            return {
                "category": "Freelance Income",
                "confidence": 0.55,
                "method": "Income Heuristic",
                "reason": "Heuristic: Unmatched credit description defaulted to Freelance Income (55% confidence)",
            }

        return {
            "category": "Other",
            "confidence": 0.50,
            "method": "Fallback",
            "reason": "No specific merchant keyword or ML pattern matched; assigned to 'Other'.",
        }


categorizer = CategorizationEngine()


def categorize_transaction(
    description: str,
    tx_type: str = "expense",
    amount: Optional[float] = None,
    db: Optional[Session] = None,
) -> Dict[str, object]:
    """Public helper to categorize a transaction."""
    return categorizer.categorize(description=description, tx_type=tx_type, amount=amount, db=db)
