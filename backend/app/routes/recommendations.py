"""AI Financial Recommendations & Personalized Category Budgets API Routes."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FinancialBudget
from app.schemas import BudgetUpdateRequest, VALID_CATEGORIES
from app.services.recommendations import generate_recommendations_and_budgets

router = APIRouter(prefix="/api/recommendations", tags=["Recommendations & Budgets"])


@router.get("", status_code=status.HTTP_200_OK)
def get_recommendations(db: Session = Depends(get_db)):
    """Retrieve personalized category spending limits, saving opportunities, excessive spend alerts, and warnings."""
    return generate_recommendations_and_budgets(db)


@router.put("/budgets", status_code=status.HTTP_200_OK)
def update_category_budget(
    payload: BudgetUpdateRequest,
    db: Session = Depends(get_db),
):
    """Customize a monthly category spending limit."""
    cat = payload.category.strip()
    if cat not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category '{cat}'. Valid categories: {', '.join(VALID_CATEGORIES)}",
        )

    budget = db.query(FinancialBudget).filter(FinancialBudget.category == cat).first()
    cur_ym = f"{date.today().year:04d}-{date.today().month:02d}"

    if budget:
        budget.monthly_limit = round(float(payload.monthly_limit), 2)
        budget.is_custom = True
    else:
        budget = FinancialBudget(
            category=cat,
            monthly_limit=round(float(payload.monthly_limit), 2),
            recommended_limit=round(float(payload.monthly_limit), 2),
            current_spent=0.0,
            previous_month_spent=0.0,
            period_month=cur_ym,
            is_custom=True,
            explanation="Custom monthly budget configured by user.",
        )
        db.add(budget)

    db.commit()
    updated_bundle = generate_recommendations_and_budgets(db)
    return {
        "message": f"Monthly budget for '{cat}' updated to ₹{payload.monthly_limit:,.0f}.",
        "data": updated_bundle,
    }
