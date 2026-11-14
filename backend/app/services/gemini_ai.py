"""Google Gemini AI Financial Assistant Service for FinPilot AI.

Security & Reliability Guarantees:
- Reads GEMINI_API_KEY and GEMINI_MODEL strictly from backend/.env or environment variables.
- Never logs, prints, or returns raw API keys.
- Uses the official Gemini Developer API endpoint with `x-goog-api-key` header authentication.
- Grounds every response in the user's actual SQLite transactions, budgets, recurring payments,
  cash flow forecasts, and anomalies.
- Provides a clear status indicator and rich data-backed local fallback when GEMINI_API_KEY is not configured
  or when API quota/network timeouts occur.
"""
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.services.recurring import detect_and_sync_recurring_payments
from app.services.forecasting import generate_cashflow_forecast
from app.services.anomaly import detect_spending_anomalies
from app.services.recommendations import generate_recommendations_and_budgets

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = BACKEND_DIR / ".env"
ROOT_ENV_PATH = BACKEND_DIR.parent / ".env"

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
PLACEHOLDER_KEYS = {
    "",
    "your_gemini_api_key_here",
    "your-api-key",
    "replace_with_your_key",
    "none",
    "null",
}


def _load_env_safely() -> None:
    """Reload backend/.env so newly added keys are picked up without exposing secrets."""
    if ENV_FILE_PATH.exists():
        load_dotenv(dotenv_path=ENV_FILE_PATH, override=True)
    elif ROOT_ENV_PATH.exists():
        load_dotenv(dotenv_path=ROOT_ENV_PATH, override=False)


def get_ai_configuration_status() -> Dict[str, Any]:
    """Return safe AI configuration metadata without exposing any secret key."""
    _load_env_safely()
    raw_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    model_name = (os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL

    is_configured = bool(raw_key) and raw_key.lower() not in PLACEHOLDER_KEYS and len(raw_key) >= 15

    return {
        "configured": is_configured,
        "ai_configured": is_configured,
        "status": "ready" if is_configured else "not_configured",
        "model": model_name,
        "provider": "Google Gemini Developer API",
        "env_file_path": "backend/.env",
        "message": (
            f"Google Gemini AI ({model_name}) is configured and active."
            if is_configured
            else "AI not configured: Set GEMINI_API_KEY in backend/.env to enable live Gemini responses. Intelligent local data-driven fallback is active."
        ),
    }


def build_financial_context_snapshot(db: Session) -> Dict[str, Any]:
    """Collect a real-time snapshot of the user's financial data from SQLite."""
    rec_bundle = generate_recommendations_and_budgets(db)
    forecast = generate_cashflow_forecast(db, horizon_days=90)
    recurring = detect_and_sync_recurring_payments(db)
    anomalies = detect_spending_anomalies(db)

    h7 = forecast.get("horizons", {}).get("7_days", {})
    h30 = forecast.get("horizons", {}).get("30_days", {})
    h90 = forecast.get("horizons", {}).get("90_days", {})

    return {
        "has_data": bool(rec_bundle.get("sufficient_data")),
        "reference_month": rec_bundle.get("reference_month", "Current"),
        "previous_month": rec_bundle.get("previous_month", "Previous"),
        "current_balance": rec_bundle.get("current_balance", 0.0),
        "monthly_income_estimate": rec_bundle.get("monthly_income_estimate", 0.0),
        "monthly_expense_estimate": rec_bundle.get("monthly_expense_estimate", 0.0),
        "monthly_surplus_estimate": rec_bundle.get("monthly_surplus_estimate", 0.0),
        "savings_rate_percent": rec_bundle.get("savings_rate_percent", 0.0),
        "financial_health_score": rec_bundle.get("financial_health_score", 0),
        "health_label": rec_bundle.get("health_label", "N/A"),
        "potential_monthly_savings": rec_bundle.get("potential_monthly_savings", 0.0),
        "category_budgets": (rec_bundle.get("category_budgets") or [])[:8],
        "recommendations": (rec_bundle.get("recommendations") or [])[:5],
        "excessive_spending": (rec_bundle.get("excessive_spending") or [])[:5],
        "upcoming_warnings": (rec_bundle.get("upcoming_payment_warnings") or [])[:5],
        "recurring_summary": recurring.get("summary", {}),
        "recurring_items": (recurring.get("recurring_payments") or [])[:8],
        "forecast_7d": h7,
        "forecast_30d": h30,
        "forecast_90d": h90,
        "forecast_confidence_level": forecast.get("confidence_level", "N/A"),
        "negative_balance_in_days": forecast.get("negative_balance_in_days"),
        "risk_warnings": forecast.get("risk_warnings", []),
        "anomalies": (anomalies.get("anomalies") or [])[:5],
        "anomalies_summary": anomalies.get("summary", {}),
    }


def _format_context_prompt(ctx: Dict[str, Any]) -> str:
    """Format the SQLite financial snapshot into a structured prompt for Gemini."""
    if not ctx.get("has_data"):
        return (
            "USER FINANCIAL SNAPSHOT: The database currently has 0 transactions. "
            "Encourage the user to add transactions or click 'Seed Demo Data' to analyze their finances."
        )

    budgets_lines = "\n".join(
        f"  - {b['category']}: Spent ₹{b['current_spent']:,.0f} in {ctx['reference_month']} "
        f"(Prev month: ₹{b['previous_month_spent']:,.0f}, MoM: {b['mom_change_percent']:+.1f}%, "
        f"Limit: ₹{b['monthly_limit']:,.0f}, Status: {b['status']})"
        for b in ctx["category_budgets"]
    )
    recurring_lines = "\n".join(
        f"  - {r['name']} ({r['recurring_type']} / {r['category']}): ₹{r['average_amount']:,.0f} "
        f"({r['frequency']}), Next Due: {r['next_payment_date']} (in {r['days_until_due']} days)"
        for r in ctx["recurring_items"]
    )
    anomaly_lines = "\n".join(
        f"  - [{a['severity']}] {a['date']} {a['description']} ({a['category']}): ₹{a['amount']:,.0f} — {a['explanation']}"
        for a in ctx["anomalies"]
    )
    rec_lines = "\n".join(
        f"  - {r['title']}: Save ₹{r['potential_monthly_savings']:,.0f}/mo — {r['explanation']}"
        for r in ctx["recommendations"]
    )

    f7 = ctx["forecast_7d"]
    f30 = ctx["forecast_30d"]
    f90 = ctx["forecast_90d"]

    return f"""You are FinPilot AI, an expert, empathetic, and data-driven personal financial advisor for Indian users.
Always use Indian Rupees (₹) formatting and cite the exact numbers from the user's live financial database below.
Never invent fake transactions. Keep your explanation clear, well-structured (using concise bullet points and bold highlights), and actionable.

=== LIVE SQLITE FINANCIAL DATA SNAPSHOT ===
- Current Account Balance: ₹{ctx['current_balance']:,.2f}
- Financial Health Score: {ctx['financial_health_score']}/100 ({ctx['health_label']})
- Estimated Monthly Income: ₹{ctx['monthly_income_estimate']:,.0f}
- Estimated Monthly Expenses: ₹{ctx['monthly_expense_estimate']:,.0f}
- Monthly Net Surplus: ₹{ctx['monthly_surplus_estimate']:,.0f} (Savings Rate: {ctx['savings_rate_percent']}%)
- Total Potential Monthly Savings Identified: ₹{ctx['potential_monthly_savings']:,.0f}/month

=== CATEGORY SPENDING & BUDGETS ({ctx['reference_month']} vs {ctx['previous_month']}) ===
{budgets_lines or '  - No category budgets yet.'}

=== RECURRING PAYMENTS & SUBSCRIPTIONS ===
- Total Monthly Recurring Outflow: ₹{ctx['recurring_summary'].get('total_monthly_recurring_expense', 0):,.0f}
- Monthly Subscriptions Total: ₹{ctx['recurring_summary'].get('subscriptions_total', 0):,.0f}
- Monthly EMIs Total: ₹{ctx['recurring_summary'].get('emi_total', 0):,.0f}
- Monthly Utility/Rent Bills Total: ₹{ctx['recurring_summary'].get('bills_total', 0):,.0f}
{recurring_lines or '  - No recurring streams detected.'}

=== CASH FLOW FORECASTS ({ctx['forecast_confidence_level']} Confidence) ===
- 7-Day Forecast: Closing Balance ₹{f7.get('predicted_balance', 0):,.0f} (Income: +₹{f7.get('predicted_income', 0):,.0f}, Expense: -₹{f7.get('predicted_expense', 0):,.0f}, Band: ±₹{f7.get('uncertainty_margin', 0):,.0f})
- 30-Day Forecast: Closing Balance ₹{f30.get('predicted_balance', 0):,.0f} (Income: +₹{f30.get('predicted_income', 0):,.0f}, Expense: -₹{f30.get('predicted_expense', 0):,.0f}, Band: ±₹{f30.get('uncertainty_margin', 0):,.0f})
- 90-Day Forecast: Closing Balance ₹{f90.get('predicted_balance', 0):,.0f} (Income: +₹{f90.get('predicted_income', 0):,.0f}, Expense: -₹{f90.get('predicted_expense', 0):,.0f}, Band: ±₹{f90.get('uncertainty_margin', 0):,.0f})
- Negative Balance Risk: {f"In {ctx['negative_balance_in_days']} days" if ctx.get('negative_balance_in_days') else "None projected in next 90 days"}

=== FLAGGED SPENDING ANOMALIES ===
{anomaly_lines or '  - No anomalies flagged.'}

=== TOP AI SAVING RECOMMENDATIONS ===
{rec_lines or '  - No recommendations yet.'}
"""


def _build_local_data_driven_fallback(
    user_message: str, ctx: Dict[str, Any], status_reason: str
) -> str:
    """Generate a personalized answer directly from the user's SQLite financial data when Gemini is not configured."""
    if not ctx.get("has_data"):
        return (
            f"**[{status_reason}]**\n\n"
            "Your database currently has no transactions. Please add income/expense transactions on the "
            "**Transactions** page or click **Seed Demo** in the sidebar to populate sample Indian Rupee (₹) data."
        )

    q = user_message.lower()
    lines = [
        f"*(Note: {status_reason} Below is your personalized analysis generated directly from your FinPilot AI SQLite database.)*\n"
    ]

    if any(k in q for k in ("forecast", "predict", "cash flow", "cashflow", "future", "balance", "risk", "30", "90")):
        f7 = ctx["forecast_7d"]
        f30 = ctx["forecast_30d"]
        f90 = ctx["forecast_90d"]
        lines.append("### 📈 Cash Flow & Balance Forecast Analysis")
        lines.append(
            f"- **Current Liquid Balance**: **₹{ctx['current_balance']:,.0f}** (Health Score: **{ctx['financial_health_score']}/100 – {ctx['health_label']}**)"
        )
        lines.append(
            f"- **7-Day Projection**: **₹{f7.get('predicted_balance', 0):,.0f}** (±₹{f7.get('uncertainty_margin', 0):,.0f} uncertainty margin)"
        )
        lines.append(
            f"- **30-Day Projection**: **₹{f30.get('predicted_balance', 0):,.0f}** (Projected Inflow: +₹{f30.get('predicted_income', 0):,.0f}, Outflow: -₹{f30.get('predicted_expense', 0):,.0f})"
        )
        lines.append(
            f"- **90-Day Projection**: **₹{f90.get('predicted_balance', 0):,.0f}** (±₹{f90.get('uncertainty_margin', 0):,.0f})"
        )
        if ctx.get("negative_balance_in_days"):
            lines.append(
                f"- ⚠️ **Liquidity Alert**: Your balance is projected to turn negative in **{ctx['negative_balance_in_days']} days**."
            )
        else:
            lines.append(
                "- ✅ **Liquidity Status**: Your baseline balance remains positive across all 7, 30, and 90-day horizons."
            )

    elif any(k in q for k in ("recurring", "subscription", "bill", "emi", "loan", "netflix", "rent")):
        rs = ctx["recurring_summary"]
        lines.append("### ↻ Recurring Payments, Subscriptions & EMI Breakdown")
        lines.append(
            f"- **Total Monthly Recurring Outflow**: **₹{rs.get('total_monthly_recurring_expense', 0):,.0f}/month**"
        )
        lines.append(
            f"  - **Subscriptions**: ₹{rs.get('subscriptions_total', 0):,.0f}/mo\n"
            f"  - **Utility & Rent Bills**: ₹{rs.get('bills_total', 0):,.0f}/mo\n"
            f"  - **Loan EMIs**: ₹{rs.get('emi_total', 0):,.0f}/mo"
        )
        lines.append("\n**Upcoming Active Streams:**")
        for r in ctx["recurring_items"][:6]:
            lines.append(
                f"- **{r['name']}** ({r['recurring_type']}): **₹{r['average_amount']:,.0f}** ({r['frequency']}) — Next due on **{r['next_payment_date']}** ({r['days_until_due']} days)"
            )

    elif any(k in q for k in ("anomal", "unusual", "spike", "outlier", "high", "alert", "flag")):
        lines.append("### 🚨 Unusual Spending & Anomaly Analysis")
        if not ctx["anomalies"]:
            lines.append("- No unusual spending outliers were flagged in your recent history.")
        else:
            for a in ctx["anomalies"][:5]:
                lines.append(
                    f"- **{a['description']}** ({a['date']}): **₹{a['amount']:,.0f}** [{a['severity']} Severity] — {a['explanation']}"
                )

    elif any(k in q for k in ("save", "saving", "budget", "limit", "reduce", "cut", "recommend", "spend")):
        lines.append("### 💡 Personalized Budget & Saving Opportunities")
        lines.append(
            f"- **Total Identified Savings Potential**: **₹{ctx['potential_monthly_savings']:,.0f}/month** (**₹{ctx['potential_monthly_savings'] * 12:,.0f}/year**)"
        )
        lines.append(
            f"- **Current Monthly Surplus**: **₹{ctx['monthly_surplus_estimate']:,.0f}** ({ctx['savings_rate_percent']}% savings rate)"
        )
        lines.append("\n**Actionable Recommendations:**")
        for r in ctx["recommendations"][:4]:
            lines.append(f"- **{r['title']}**: {r['explanation']}")
        lines.append("\n**Category Budget Utilization:**")
        for b in ctx["category_budgets"][:5]:
            lines.append(
                f"- **{b['category']}**: ₹{b['current_spent']:,.0f} / ₹{b['monthly_limit']:,.0f} ({b['utilization_percent']}% used, {b['mom_change_percent']:+.1f}% MoM)"
            )

    else:
        lines.append("### 📊 Complete Financial Health & Executive Summary")
        lines.append(
            f"- **Current Balance**: **₹{ctx['current_balance']:,.0f}** | **Health Score**: **{ctx['financial_health_score']}/100 ({ctx['health_label']})**"
        )
        lines.append(
            f"- **Monthly Cash Flow**: Income **₹{ctx['monthly_income_estimate']:,.0f}** vs Expenses **₹{ctx['monthly_expense_estimate']:,.0f}** → Net Surplus **₹{ctx['monthly_surplus_estimate']:,.0f}/mo** ({ctx['savings_rate_percent']}%)"
        )
        lines.append(
            f"- **30-Day Predicted Balance**: **₹{ctx['forecast_30d'].get('predicted_balance', 0):,.0f}**"
        )
        lines.append(
            f"- **Recurring Commitments**: **₹{ctx['recurring_summary'].get('total_monthly_recurring_expense', 0):,.0f}/mo** (Subscriptions: ₹{ctx['recurring_summary'].get('subscriptions_total', 0):,.0f}, EMIs: ₹{ctx['recurring_summary'].get('emi_total', 0):,.0f})"
        )
        if ctx["recommendations"]:
            top_r = ctx["recommendations"][0]
            lines.append(f"- **Top Saving Opportunity**: {top_r['title']} — {top_r['explanation']}")

    return "\n".join(lines)


async def chat_with_financial_assistant(
    db: Session,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Process a user query using Google Gemini Developer API grounded in real SQLite financial data."""
    _load_env_safely()
    status_info = get_ai_configuration_status()
    ctx = build_financial_context_snapshot(db)

    suggested_questions = [
        "Where is my money going this month and which categories increased?",
        "How much can I save each month based on my actual transactions?",
        "Explain my 30-day and 90-day cash flow forecast and any liquidity risks.",
        "List all my recurring subscriptions, utility bills, and EMIs.",
        "Why were some of my recent transactions flagged as unusual anomalies?",
    ]

    if not status_info["configured"]:
        fallback_reply = _build_local_data_driven_fallback(
            user_message=user_message,
            ctx=ctx,
            status_reason="AI not configured (GEMINI_API_KEY missing in backend/.env)",
        )
        return {
            "reply": fallback_reply,
            "ai_configured": False,
            "source": "local_fallback",
            "mode": "local_fallback",
            "model": status_info["model"],
            "ai_notice": "Local Data-Driven Engine (GEMINI_API_KEY not configured)",
            "status_message": status_info["message"],
            "suggested_questions": suggested_questions,
            "context_summary": {
                "current_balance": ctx["current_balance"],
                "health_score": ctx["financial_health_score"],
                "potential_monthly_savings": ctx["potential_monthly_savings"],
            },
        }

    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    configured_model = status_info["model"]
    system_prompt = _format_context_prompt(ctx)

    # Build multi-turn contents payload for Gemini Developer API
    contents = []
    for turn in (history or [])[-6:]:
        role = "model" if turn.get("role") in ("assistant", "model") else "user"
        text = (turn.get("content") or "").strip()
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})

    contents.append({"role": "user", "parts": [{"text": user_message.strip()}]})

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": 1200,
        },
    }

    # Candidate models: try user's configured model first, with safe fallback if model ID isn't available on their key
    candidate_models = [configured_model]
    for fallback_m in ("gemini-2.5-flash", "gemini-2.0-flash"):
        if fallback_m not in candidate_models:
            candidate_models.append(fallback_m)

    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }

    last_error_reason = "Gemini API temporarily unavailable"

    async with httpx.AsyncClient(timeout=20.0) as client:
        for model_id in candidate_models:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent"
            try:
                resp = await client.post(endpoint, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates") or []
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts") or []
                        reply_text = "\n".join(p.get("text", "") for p in parts if p.get("text")).strip()
                        if reply_text:
                            return {
                                "reply": reply_text,
                                "ai_configured": True,
                                "source": "gemini",
                                "mode": "gemini_live",
                                "model": model_id,
                                "ai_notice": f"Google Gemini ({model_id})",
                                "status_message": f"Powered by Google Gemini ({model_id})",
                                "suggested_questions": suggested_questions,
                                "context_summary": {
                                    "current_balance": ctx["current_balance"],
                                    "health_score": ctx["financial_health_score"],
                                    "potential_monthly_savings": ctx["potential_monthly_savings"],
                                },
                            }
                elif resp.status_code == 404:
                    last_error_reason = f"Model '{model_id}' not found on this API key tier"
                    continue
                elif resp.status_code == 429:
                    last_error_reason = "Gemini API rate limit or quota exceeded (HTTP 429)"
                    break
                elif resp.status_code in (400, 401, 403):
                    last_error_reason = "Gemini API key rejected or unauthorized (check GEMINI_API_KEY in backend/.env)"
                    break
                else:
                    last_error_reason = f"Gemini API returned HTTP {resp.status_code}"
                    break
            except httpx.TimeoutException:
                last_error_reason = "Gemini API request timed out after 20 seconds"
                break
            except Exception:
                last_error_reason = "Network error while contacting Gemini Developer API"
                break

    # Graceful fallback if Gemini returned an error/timeout so the user still gets an accurate answer
    fallback_reply = _build_local_data_driven_fallback(
        user_message=user_message,
        ctx=ctx,
        status_reason=last_error_reason,
    )
    return {
        "reply": fallback_reply,
        "ai_configured": True,
        "source": "local_fallback",
        "mode": "local_fallback_on_error",
        "model": configured_model,
        "ai_notice": f"Local Fallback ({last_error_reason})",
        "status_message": last_error_reason,
        "suggested_questions": suggested_questions,
        "context_summary": {
            "current_balance": ctx["current_balance"],
            "health_score": ctx["financial_health_score"],
            "potential_monthly_savings": ctx["potential_monthly_savings"],
        },
    }
