"""FinPilot AI – FastAPI Application Entrypoint (Production & Local Ready)."""
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import engine, Base, SessionLocal
from app.models import Transaction
from app.routes import transactions, analytics, predictions, recommendations, simulations
from app.utils.seed_demo import seed_demo_data


def initialize_database_and_demo():
    """Ensure database tables exist and seed initial demo data only if the database is empty."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        tx_count = db.query(Transaction).count()
        if tx_count == 0:
            seed_demo_data(db, reset_existing_demo=False)
    except Exception as exc:
        print(f"[FinPilot AI Startup Warning] Demo seeding skipped: {exc}")
    finally:
        db.close()


# Ensure tables exist even when imported by ASGI workers before lifespan events
initialize_database_and_demo()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify database initialization on FastAPI startup without overwriting user data."""
    initialize_database_and_demo()
    yield


app = FastAPI(
    title="FinPilot AI – Personal Financial Operating System",
    description=(
        "AI-powered financial management, automated transaction categorization, "
        "recurring payment detection, hybrid time-series cash flow forecasting, "
        "anomaly detection, personalized recommendations, and what-if financial simulations."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS for same-domain production deployment and local web servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Safe Global Exception Handlers (never expose internal stack traces to users)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        loc = " -> ".join(str(x) for x in err.get("loc", []) if x != "body")
        msg = err.get("msg", "Invalid input")
        errors.append(f"{loc}: {msg}" if loc else msg)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "validation_error",
            "detail": "; ".join(errors) if errors else "Invalid request parameters.",
            "errors": errors,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "detail": "An unexpected server error occurred while processing your request. Please verify your input and try again.",
        },
    )


# Health Check Endpoint
@app.get("/api/health", tags=["System"], status_code=status.HTTP_200_OK)
def health_check():
    """Return system health, database status, and active timestamp."""
    db = SessionLocal()
    try:
        total_tx = db.query(Transaction).count()
        demo_tx = db.query(Transaction).filter(Transaction.is_demo == True).count()
        user_tx = total_tx - demo_tx
        db_status = "connected"
    except Exception:
        total_tx = 0
        demo_tx = 0
        user_tx = 0
        db_status = "degraded"
    finally:
        db.close()

    return {
        "status": "healthy",
        "service": "FinPilot AI Backend",
        "version": "1.0.0",
        "database": db_status,
        "transactions_count": total_tx,
        "demo_transactions_count": demo_tx,
        "user_transactions_count": user_tx,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# Register API Routers
app.include_router(transactions.router)
app.include_router(analytics.router)
app.include_router(predictions.router)
app.include_router(recommendations.router)
app.include_router(simulations.router)

# Serve Frontend HTML, CSS, and JS from the Same Domain
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
FRONTEND_PAGES = {
    "index",
    "dashboard",
    "transactions",
    "analytics",
    "predictions",
    "recommendations",
    "simulations",
}

if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")

    @app.get("/", include_in_schema=False)
    def serve_root():
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file), media_type="text/html")
        return {"message": "FinPilot AI API is running. Visit /docs for API documentation."}

    @app.get("/{page_name}.html", include_in_schema=False)
    def serve_html_page(page_name: str):
        if page_name in FRONTEND_PAGES:
            target = FRONTEND_DIR / f"{page_name}.html"
            if target.exists():
                return FileResponse(str(target), media_type="text/html")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    @app.get("/{page_name}", include_in_schema=False)
    def serve_clean_page_route(page_name: str):
        if page_name in FRONTEND_PAGES:
            target = FRONTEND_DIR / f"{page_name}.html"
            if target.exists():
                return FileResponse(str(target), media_type="text/html")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
