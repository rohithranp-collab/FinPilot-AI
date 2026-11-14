"""Cash Flow Forecasting, Prediction Accuracy & Anomaly Detection API Routes."""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.forecasting import generate_cashflow_forecast, evaluate_prediction_accuracy
from app.services.anomaly import detect_spending_anomalies

router = APIRouter(tags=["Predictions & Anomalies"])


@router.get("/api/predictions/cashflow", status_code=status.HTTP_200_OK)
def get_cashflow_predictions(
    horizon: int = Query(90, ge=7, le=90, description="Forecast horizon in days (7, 30, or 90)"),
    db: Session = Depends(get_db),
):
    """Forecast upcoming income, expenses, and account balance for 7-day, 30-day, and 90-day horizons."""
    return generate_cashflow_forecast(db, horizon_days=horizon)


@router.get("/api/predictions/accuracy", status_code=status.HTTP_200_OK)
def get_prediction_accuracy(db: Session = Depends(get_db)):
    """Compare previous forecasts and walk-forward backtests against actual transactions (MAE, RMSE, MAPE)."""
    return evaluate_prediction_accuracy(db)


@router.get("/api/anomalies", status_code=status.HTTP_200_OK)
def get_spending_anomalies(db: Session = Depends(get_db)):
    """Detect unusually high expenses and spending frequency bursts with historical comparisons."""
    return detect_spending_anomalies(db)
