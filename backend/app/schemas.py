"""Pydantic validation schemas for FinPilot AI REST APIs."""
from datetime import date as DateType, datetime as DateTimeType
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator


VALID_CATEGORIES = [
    "Food",
    "Shopping",
    "Transportation",
    "Healthcare",
    "Entertainment",
    "Education",
    "Rent",
    "Utilities",
    "EMI and Loans",
    "Salary",
    "Freelance Income",
    "Other",
]


class TransactionBase(BaseModel):
    date: DateType = Field(..., description="Transaction date in YYYY-MM-DD format")
    amount: float = Field(..., gt=0, description="Transaction amount in INR (must be > 0)")
    description: str = Field(..., min_length=1, max_length=255, description="Merchant or description")
    type: Literal["income", "expense"] = Field(..., description="Transaction type: 'income' or 'expense'")
    category: Optional[str] = Field(
        None,
        description="Optional category. If omitted or 'Auto', automatic AI categorization is applied.",
    )
    payment_method: Optional[str] = Field("UPI / Bank", max_length=50)
    is_demo: Optional[bool] = Field(False)

    @field_validator("description")
    @classmethod
    def clean_description(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Transaction description cannot be empty.")
        return cleaned

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v <= 0 or v > 1_000_000_000:
            raise ValueError("Amount must be greater than 0 and less than ₹1,00,00,00,000.")
        return round(float(v), 2)


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    date: Optional[DateType] = None
    amount: Optional[float] = Field(None, gt=0)
    description: Optional[str] = Field(None, min_length=1, max_length=255)
    type: Optional[Literal["income", "expense"]] = None
    category: Optional[str] = None
    payment_method: Optional[str] = Field(None, max_length=50)

    @field_validator("description")
    @classmethod
    def clean_description(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Transaction description cannot be empty.")
            return cleaned
        return v


class TransactionResponse(BaseModel):
    id: int
    date: DateType
    amount: float
    description: str
    type: str
    category: str
    auto_categorized: bool
    categorization_reason: Optional[str] = None
    payment_method: str
    is_demo: bool
    recurring_payment_id: Optional[int] = None
    created_at: Optional[DateTimeType] = None

    class Config:
        from_attributes = True


class CategorizePreviewRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=255)
    type: Literal["income", "expense"] = "expense"
    amount: Optional[float] = None


class RecurringPaymentResponse(BaseModel):
    id: int
    name: str
    category: str
    type: str
    recurring_type: str
    average_amount: float
    frequency: str
    interval_days: int
    last_payment_date: DateType
    next_payment_date: DateType
    days_until_due: int
    confidence: float
    occurrences: int
    status: str
    is_demo: bool


class BudgetUpdateRequest(BaseModel):
    category: str
    monthly_limit: float = Field(..., gt=0)


class SimulationCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    scenario_type: Literal[
        "large_purchase",
        "loan_repayment",
        "monthly_emi",
        "savings_target",
        "additional_expense",
    ]
    total_amount: float = Field(..., gt=0, description="Primary rupee amount for the scenario")
    duration_months: int = Field(12, ge=1, le=360, description="Duration or horizon in months")
    interest_rate: float = Field(0.0, ge=0.0, le=50.0, description="Annual interest rate (%) for loans/EMI")
    down_payment: float = Field(0.0, ge=0.0, description="Optional initial down payment or upfront lump sum")
    existing_emi: float = Field(0.0, ge=0.0, description="Optional existing monthly EMI for loan prepayment comparison")
    extra_monthly_payment: float = Field(0.0, ge=0.0, description="Optional extra monthly payment towards loan")
    start_month_offset: int = Field(0, ge=0, le=12, description="Months from today when decision starts")


class SimulationResponse(BaseModel):
    id: int
    name: str
    scenario_type: str
    total_amount: float
    monthly_impact: float
    one_time_impact: float
    duration_months: int
    interest_rate: float
    current_balance_baseline: float
    projected_balance_before: float
    projected_balance_after: float
    net_worth_delta: float
    risk_level: str
    verdict: str
    details: Dict[str, Any]
    is_demo: bool
    created_at: Optional[DateTimeType] = None
