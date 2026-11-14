"""Smart Financial OS API Routes (12 Hackathon-Winning Features)."""
from datetime import date as DateType
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Transaction, RecurringPayment
from app.schemas import TransactionResponse
from app.services.sms_voice_parser import parse_indian_bank_sms, parse_voice_command_hinglish
from app.services.hackathon_features import get_complete_smart_os_bundle
from app.services.recurring import detect_and_sync_recurring_payments

router = APIRouter(tags=["Smart Financial OS (12 Unique Features)"])


class SMSParseRequest(BaseModel):
    sms_text: str = Field(..., min_length=4, max_length=1500, description="Raw Indian Bank or UPI SMS text")
    auto_save: bool = Field(False, description="Whether to immediately save the parsed transaction into SQLite")


class VoiceParseRequest(BaseModel):
    transcript: str = Field(..., min_length=3, max_length=1000, description="Spoken English or Hinglish expense command")
    auto_save: bool = Field(False, description="Whether to immediately save the parsed transaction into SQLite")


@router.get("/api/smart/overview", status_code=status.HTTP_200_OK)
def get_smart_os_overview(
    stress_test: bool = Query(False, description="Simulate a 15-day liquidity emergency to test Panic Mode"),
    db: Session = Depends(get_db),
):
    """Return all 12 Smart Financial OS features computed from live SQLite data."""
    return get_complete_smart_os_bundle(db, simulate_stress=stress_test)


@router.post("/api/transactions/parse-sms", status_code=status.HTTP_200_OK)
def parse_and_ingest_sms(payload: SMSParseRequest, db: Session = Depends(get_db)):
    """Feature #2: Parse an Indian Bank / UPI / WhatsApp SMS and optionally store the transaction."""
    try:
        parsed = parse_indian_bank_sms(payload.sms_text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    saved_tx = None
    if payload.auto_save:
        tx_row = Transaction(
            date=DateType.fromisoformat(parsed["date"]),
            amount=float(parsed["amount"]),
            description=parsed["description"],
            type=parsed["type"],
            category=parsed["category"],
            auto_categorized=True,
            categorization_reason=f"SMS Auto-Reader ({parsed['detected_bank']}): {parsed['categorization_reason']}",
            payment_method=parsed["payment_method"],
            is_demo=False,
        )
        db.add(tx_row)
        db.commit()
        db.refresh(tx_row)
        detect_and_sync_recurring_payments(db)
        saved_tx = TransactionResponse.model_validate(tx_row).model_dump(mode="json")

    return {
        "parsed": parsed,
        "auto_saved": payload.auto_save,
        "transaction": saved_tx,
        "message": (
            f"Parsed & saved {parsed['type']} of ₹{parsed['amount']:,.2f} at {parsed['merchant']} ({parsed['category']})."
            if payload.auto_save
            else f"Parsed {parsed['type']} of ₹{parsed['amount']:,.2f} at {parsed['merchant']} ({parsed['category']})."
        ),
    }


@router.post("/api/transactions/parse-voice", status_code=status.HTTP_200_OK)
def parse_and_ingest_voice(payload: VoiceParseRequest, db: Session = Depends(get_db)):
    """Feature #7: Parse an English or Hinglish voice transcript and optionally store the transaction."""
    try:
        parsed = parse_voice_command_hinglish(payload.transcript)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    saved_tx = None
    if payload.auto_save:
        tx_row = Transaction(
            date=DateType.fromisoformat(parsed["date"]),
            amount=float(parsed["amount"]),
            description=parsed["description"],
            type=parsed["type"],
            category=parsed["category"],
            auto_categorized=True,
            categorization_reason=f"Voice Entry ({parsed['date_label']}): {parsed['categorization_reason']}",
            payment_method=parsed["payment_method"],
            is_demo=False,
        )
        db.add(tx_row)
        db.commit()
        db.refresh(tx_row)
        detect_and_sync_recurring_payments(db)
        saved_tx = TransactionResponse.model_validate(tx_row).model_dump(mode="json")

    return {
        "parsed": parsed,
        "auto_saved": payload.auto_save,
        "transaction": saved_tx,
        "message": (
            f"Voice entry saved: ₹{parsed['amount']:,.2f} for {parsed['description']} ({parsed['category']}) on {parsed['date']}."
            if payload.auto_save
            else f"Voice entry parsed: ₹{parsed['amount']:,.2f} for {parsed['description']} ({parsed['category']}) on {parsed['date']}."
        ),
    }


@router.post("/api/smart/cancel-subscription/{sub_id}", status_code=status.HTTP_200_OK)
def cancel_subscription_one_click(sub_id: int, db: Session = Depends(get_db)):
    """Feature #1: Mark a recurring subscription as Cancelled in 1 click and report annual savings."""
    rec = db.query(RecurringPayment).filter(RecurringPayment.id == sub_id).first()
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Subscription #{sub_id} not found.")

    rec.status = "Cancelled"
    db.commit()
    annual_saved = round(float(rec.average_amount) * 12, 2)
    return {
        "id": rec.id,
        "name": rec.name,
        "status": "Cancelled",
        "monthly_saved": round(float(rec.average_amount), 2),
        "annual_saved": annual_saved,
        "message": f"Auto-debit cancellation flagged for '{rec.name}'. Estimated savings: ₹{rec.average_amount:,.0f}/mo (₹{annual_saved:,.0f}/year)!",
    }
