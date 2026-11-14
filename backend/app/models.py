"""SQLAlchemy ORM models for FinPilot AI."""
from datetime import datetime, date
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    Date,
    DateTime,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship
from app.database import Base


class RecurringPayment(Base):
    """Detected or registered recurring payments (subscriptions, bills, income, EMIs)."""

    __tablename__ = "recurring_payments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    category = Column(String(50), nullable=False)
    type = Column(String(20), nullable=False)  # 'income' or 'expense'
    recurring_type = Column(
        String(50), nullable=False
    )  # 'Subscription', 'Recurring Bill', 'Regular Income', 'EMI Payment'
    average_amount = Column(Float, nullable=False)
    frequency = Column(String(30), nullable=False, default="Monthly")
    interval_days = Column(Integer, nullable=False, default=30)
    last_payment_date = Column(Date, nullable=False)
    next_payment_date = Column(Date, nullable=False, index=True)
    confidence = Column(Float, nullable=False, default=0.85)
    occurrences = Column(Integer, nullable=False, default=2)
    status = Column(String(20), nullable=False, default="Active")
    is_demo = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = relationship(
        "Transaction",
        back_populates="recurring_payment",
        passive_deletes=True,
    )


class Transaction(Base):
    """Individual income and expense transactions."""

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True, default=date.today)
    amount = Column(Float, nullable=False)
    description = Column(String(255), nullable=False)
    type = Column(String(20), nullable=False, index=True)  # 'income' or 'expense'
    category = Column(String(50), nullable=False, index=True)
    auto_categorized = Column(Boolean, nullable=False, default=True)
    categorization_reason = Column(String(255), nullable=True)
    payment_method = Column(String(50), nullable=False, default="UPI / Bank")
    is_demo = Column(Boolean, nullable=False, default=False, index=True)
    recurring_payment_id = Column(
        Integer,
        ForeignKey("recurring_payments.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    recurring_payment = relationship("RecurringPayment", back_populates="transactions")

    __table_args__ = (
        Index("idx_transactions_date_type", "date", "type"),
        Index("idx_transactions_category_type", "category", "type"),
    )


class FinancialBudget(Base):
    """Personalized and AI-recommended monthly category spending budgets."""

    __tablename__ = "financial_budgets"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(50), nullable=False, unique=True, index=True)
    monthly_limit = Column(Float, nullable=False)
    recommended_limit = Column(Float, nullable=False)
    current_spent = Column(Float, nullable=False, default=0.0)
    previous_month_spent = Column(Float, nullable=False, default=0.0)
    period_month = Column(String(7), nullable=False)  # YYYY-MM
    is_custom = Column(Boolean, nullable=False, default=False)
    explanation = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Prediction(Base):
    """Historical and active cash flow forecast records for accuracy tracking."""

    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    forecast_origin_date = Column(Date, nullable=False)
    target_date = Column(Date, nullable=False, index=True)
    horizon_days = Column(Integer, nullable=False)  # 7, 30, 90
    predicted_income = Column(Float, nullable=False)
    predicted_expense = Column(Float, nullable=False)
    predicted_net_flow = Column(Float, nullable=False)
    predicted_balance = Column(Float, nullable=False)
    lower_bound_balance = Column(Float, nullable=False)
    upper_bound_balance = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    methodology = Column(String(120), nullable=False)
    actual_income = Column(Float, nullable=True)
    actual_expense = Column(Float, nullable=True)
    actual_balance = Column(Float, nullable=True)
    is_demo = Column(Boolean, nullable=False, default=False)


class Simulation(Base):
    """Saved what-if financial decision simulations."""

    __tablename__ = "simulations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    scenario_type = Column(
        String(50), nullable=False
    )  # 'large_purchase', 'loan_repayment', 'monthly_emi', 'savings_target', 'additional_expense'
    total_amount = Column(Float, nullable=False)
    monthly_impact = Column(Float, nullable=False)
    one_time_impact = Column(Float, nullable=False, default=0.0)
    duration_months = Column(Integer, nullable=False, default=12)
    interest_rate = Column(Float, nullable=False, default=0.0)
    current_balance_baseline = Column(Float, nullable=False)
    projected_balance_before = Column(Float, nullable=False)
    projected_balance_after = Column(Float, nullable=False)
    net_worth_delta = Column(Float, nullable=False, default=0.0)
    risk_level = Column(String(30), nullable=False)  # 'Low', 'Moderate', 'High', 'Critical'
    verdict = Column(Text, nullable=False)
    parameters_json = Column(Text, nullable=True)
    is_demo = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
