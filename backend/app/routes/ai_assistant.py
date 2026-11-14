"""AI Financial Assistant & Gemini Status API Routes."""
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.gemini_ai import (
    get_ai_configuration_status,
    chat_with_financial_assistant,
    build_financial_context_snapshot,
)

router = APIRouter(tags=["AI Financial Assistant"])


class AIChatMessage(BaseModel):
    role: str = Field("user", description="Message role: 'user' or 'assistant'")
    content: str = Field(..., min_length=1, max_length=4000)


class AIChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User question for FinPilot AI")
    history: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="Optional prior conversation turns [{'role': 'user'|'assistant', 'content': '...'}]",
    )

    @field_validator("message")
    @classmethod
    def validate_non_empty_message(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Question message cannot be empty.")
        return cleaned


@router.get("/api/ai/status", status_code=status.HTTP_200_OK)
def get_ai_status(db: Session = Depends(get_db)):
    """Return whether Google Gemini AI is configured without exposing any API keys or secrets."""
    ai_status = get_ai_configuration_status()
    snapshot = build_financial_context_snapshot(db)
    return {
        **ai_status,
        "has_financial_data": snapshot.get("has_data", False),
        "suggested_questions": [
            "How is my overall financial health and savings rate right now?",
            "Where am I spending the most money and how can I cut back?",
            "What recurring subscriptions, bills, and EMIs are coming up soon?",
            "Am I at risk of a low balance in the next 30 or 90 days?",
            "Are there any unusual or anomalous expenses flagged in my account?",
            "What personalized monthly budget limits do you recommend for me?",
        ],
    }


@router.post("/api/ai/chat", status_code=status.HTTP_200_OK)
async def post_ai_chat(payload: AIChatRequest, db: Session = Depends(get_db)):
    """Answer user financial questions grounded in live SQLite transactions, budgets, recurring items, and forecasts."""
    return await chat_with_financial_assistant(
        db=db,
        user_message=payload.message,
        history=payload.history,
    )
