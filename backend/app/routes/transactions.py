"""Transaction Management & CSV Import API Routes."""
import csv
import io
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Request, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Transaction
from app.schemas import (
    TransactionCreate,
    TransactionUpdate,
    CategorizePreviewRequest,
    VALID_CATEGORIES,
)
from app.services.categorization import categorize_transaction
from app.services.recurring import detect_and_sync_recurring_payments
from app.utils.seed_demo import seed_demo_data, clear_demo_data

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])


def _serialize_tx(tx: Transaction) -> dict:
    return {
        "id": tx.id,
        "date": tx.date.isoformat(),
        "amount": round(float(tx.amount), 2),
        "description": tx.description,
        "type": tx.type,
        "category": tx.category,
        "auto_categorized": bool(tx.auto_categorized),
        "categorization_reason": tx.categorization_reason,
        "payment_method": tx.payment_method or "UPI / Bank",
        "is_demo": bool(tx.is_demo),
        "recurring_payment_id": tx.recurring_payment_id,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
    }


def _parse_flexible_date(val: str) -> date:
    val = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y", "%d %b %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return date.fromisoformat(val[:10])


@router.get("", status_code=status.HTTP_200_OK)
def get_transactions(
    type: Optional[str] = Query(None, description="Filter by 'income' or 'expense'"),
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search description or category"),
    start_date: Optional[date] = Query(None, description="Filter from date YYYY-MM-DD"),
    end_date: Optional[date] = Query(None, description="Filter up to date YYYY-MM-DD"),
    data_source: Optional[str] = Query(None, description="'all', 'user', or 'demo'"),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve transaction history with filtering, search, and summary counts."""
    query = db.query(Transaction)

    if type in {"income", "expense"}:
        query = query.filter(Transaction.type == type)
    if category and category != "All":
        query = query.filter(Transaction.category == category)
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if data_source == "user":
        query = query.filter(Transaction.is_demo == False)
    elif data_source == "demo":
        query = query.filter(Transaction.is_demo == True)
    if search and search.strip():
        q_term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Transaction.description.ilike(q_term),
                Transaction.category.ilike(q_term),
                Transaction.payment_method.ilike(q_term),
            )
        )

    total_matching = query.count()
    items = (
        query.order_by(Transaction.date.desc(), Transaction.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    filtered_income = sum(float(t.amount) for t in items if t.type == "income")
    filtered_expense = sum(float(t.amount) for t in items if t.type == "expense")
    demo_count = db.query(Transaction).filter(Transaction.is_demo == True).count()
    user_count = db.query(Transaction).filter(Transaction.is_demo == False).count()

    return {
        "transactions": [_serialize_tx(t) for t in items],
        "total": total_matching,
        "filtered_summary": {
            "income": round(filtered_income, 2),
            "expense": round(filtered_expense, 2),
            "net": round(filtered_income - filtered_expense, 2),
        },
        "dataset_breakdown": {
            "demo_transactions": demo_count,
            "user_transactions": user_count,
            "total_transactions": demo_count + user_count,
        },
        "categories": VALID_CATEGORIES,
    }


@router.post("/categorize-preview", status_code=status.HTTP_200_OK)
def preview_categorization(
    payload: CategorizePreviewRequest,
    db: Session = Depends(get_db),
):
    """Preview automatic AI categorization and explanation for a transaction description."""
    result = categorize_transaction(
        description=payload.description,
        tx_type=payload.type,
        amount=payload.amount,
        db=db,
    )
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
):
    """Add a new income or expense transaction with automatic categorization if category is omitted/Auto."""
    cat_info = categorize_transaction(
        description=payload.description,
        tx_type=payload.type,
        amount=payload.amount,
        db=db,
    )

    if not payload.category or payload.category.strip().lower() in {"", "auto", "automatic"}:
        final_category = str(cat_info["category"])
        auto_cat = True
        reason = str(cat_info["reason"])
    else:
        final_category = (
            payload.category.strip()
            if payload.category.strip() in VALID_CATEGORIES
            else str(cat_info["category"])
        )
        auto_cat = False
        reason = f"Manually assigned to '{final_category}' by user (AI suggested: {cat_info['category']})"

    tx = Transaction(
        date=payload.date,
        amount=round(float(payload.amount), 2),
        description=payload.description.strip(),
        type=payload.type,
        category=final_category,
        auto_categorized=auto_cat,
        categorization_reason=reason,
        payment_method=payload.payment_method or "UPI / Bank",
        is_demo=bool(payload.is_demo),
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)

    # Re-sync recurring payment detection
    detect_and_sync_recurring_payments(db)
    db.refresh(tx)

    return {
        "message": "Transaction created successfully.",
        "transaction": _serialize_tx(tx),
    }


@router.put("/{tx_id}", status_code=status.HTTP_200_OK)
def update_transaction(
    tx_id: int,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
):
    """Edit an existing transaction by ID."""
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID {tx_id} not found.",
        )

    if payload.date is not None:
        tx.date = payload.date
    if payload.amount is not None:
        tx.amount = round(float(payload.amount), 2)
    if payload.description is not None:
        tx.description = payload.description.strip()
    if payload.type is not None:
        tx.type = payload.type
    if payload.payment_method is not None:
        tx.payment_method = payload.payment_method.strip()

    if payload.category is not None:
        if payload.category.strip().lower() in {"", "auto", "automatic"}:
            cat_info = categorize_transaction(
                description=tx.description,
                tx_type=tx.type,
                amount=tx.amount,
                db=db,
            )
            tx.category = str(cat_info["category"])
            tx.auto_categorized = True
            tx.categorization_reason = str(cat_info["reason"])
        else:
            tx.category = (
                payload.category.strip()
                if payload.category.strip() in VALID_CATEGORIES
                else "Other"
            )
            tx.auto_categorized = False
            tx.categorization_reason = f"Manually updated to '{tx.category}' by user."

    db.commit()
    detect_and_sync_recurring_payments(db)
    db.refresh(tx)

    return {
        "message": "Transaction updated successfully.",
        "transaction": _serialize_tx(tx),
    }


@router.delete("/demo", status_code=status.HTTP_200_OK)
def remove_demo_transactions(db: Session = Depends(get_db)):
    """Clear all demo data (`is_demo=True`) while preserving user-entered data (`is_demo=False`)."""
    return clear_demo_data(db)


@router.post("/seed-demo", status_code=status.HTTP_200_OK)
def load_demo_transactions(db: Session = Depends(get_db)):
    """Seed realistic Indian Rupee (₹) demo data (`is_demo=True`)."""
    return seed_demo_data(db, reset_existing_demo=True)


@router.delete("/{tx_id}", status_code=status.HTTP_200_OK)
def delete_transaction(
    tx_id: int,
    db: Session = Depends(get_db),
):
    """Delete a transaction by ID."""
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID {tx_id} not found.",
        )

    db.delete(tx)
    db.commit()
    detect_and_sync_recurring_payments(db)

    return {
        "message": f"Transaction #{tx_id} deleted successfully.",
        "deleted_id": tx_id,
    }


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_transactions_csv(
    request: Request,
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """Import transactions from a CSV file upload or JSON CSV text payload.

    Expected columns (case-insensitive):
    date, amount, description, type (optional: defaults based on sign or 'expense'), category (optional: auto-categorized)
    """
    raw_csv_text = ""

    if file is not None:
        content_bytes = await file.read()
        try:
            raw_csv_text = content_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            raw_csv_text = content_bytes.decode("latin-1")
    else:
        try:
            body = await request.json()
            raw_csv_text = body.get("csv_content", "") or body.get("csv", "")
        except Exception:
            raw_csv_text = ""

    if not raw_csv_text or not raw_csv_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No CSV content provided. Upload a valid .csv file or pass 'csv_content'.",
        )

    reader = csv.DictReader(io.StringIO(raw_csv_text.strip()))
    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV header row is missing. Expected columns: date, amount, description, type, category.",
        )

    imported_records: List[Transaction] = []
    skipped_rows: List[dict] = []

    for idx, row in enumerate(reader, start=1):
        norm_row = {
            (k.strip().lower() if k else ""): (v.strip() if isinstance(v, str) else "")
            for k, v in row.items()
        }

        date_str = (
            norm_row.get("date")
            or norm_row.get("transaction_date")
            or norm_row.get("txn_date")
            or ""
        )
        desc_str = (
            norm_row.get("description")
            or norm_row.get("narration")
            or norm_row.get("particulars")
            or norm_row.get("merchant")
            or ""
        )
        amt_str = (
            norm_row.get("amount")
            or norm_row.get("value")
            or norm_row.get("inr")
            or ""
        )
        type_str = (norm_row.get("type") or norm_row.get("transaction_type") or "").lower()
        cat_str = norm_row.get("category") or ""
        method_str = norm_row.get("payment_method") or norm_row.get("mode") or "CSV Import"

        if not date_str or not desc_str or not amt_str:
            skipped_rows.append({"row": idx, "reason": "Missing date, description, or amount"})
            continue

        try:
            parsed_date = _parse_flexible_date(date_str)
            clean_amt_str = amt_str.replace("₹", "").replace(",", "").replace("INR", "").strip()
            raw_amount = float(clean_amt_str)
            if raw_amount == 0:
                skipped_rows.append({"row": idx, "reason": "Amount cannot be zero"})
                continue

            if type_str in {"income", "credit", "cr", "deposit"}:
                tx_type = "income"
            elif type_str in {"expense", "debit", "dr", "withdrawal"}:
                tx_type = "expense"
            else:
                tx_type = "income" if raw_amount > 0 and type_str == "credit" else ("expense" if raw_amount > 0 else "expense")
                if raw_amount < 0:
                    tx_type = "expense"

            amount = round(abs(raw_amount), 2)
        except Exception as exc:
            skipped_rows.append({"row": idx, "reason": f"Invalid date or amount ({exc})"})
            continue

        cat_info = categorize_transaction(
            description=desc_str,
            tx_type=tx_type,
            amount=amount,
            db=db,
        )

        if cat_str and cat_str in VALID_CATEGORIES:
            final_cat = cat_str
            auto_cat = False
            reason = f"Imported from CSV with category '{final_cat}'"
        else:
            final_cat = str(cat_info["category"])
            auto_cat = True
            reason = str(cat_info["reason"])

        tx = Transaction(
            date=parsed_date,
            amount=amount,
            description=desc_str[:255],
            type=tx_type,
            category=final_cat,
            auto_categorized=auto_cat,
            categorization_reason=reason,
            payment_method=method_str[:50],
            is_demo=False,
        )
        db.add(tx)
        imported_records.append(tx)

    if not imported_records:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No valid transactions could be imported. Skipped {len(skipped_rows)} rows.",
        )

    db.commit()
    detect_and_sync_recurring_payments(db)

    return {
        "message": f"Successfully imported {len(imported_records)} transactions.",
        "imported_count": len(imported_records),
        "skipped_count": len(skipped_rows),
        "skipped_details": skipped_rows[:15],
        "transactions": [_serialize_tx(t) for t in imported_records[:25]],
    }
