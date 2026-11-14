"""FinPilot AI – FastAPI Application Entrypoint (Production & Local Ready)."""
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

# Ensure backend directory is on sys.path whether launched from project root or backend/
_BACKEND_DIR_INIT = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR_INIT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR_INIT))

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import engine, Base, SessionLocal
from app.models import Transaction
from app.routes import (
    transactions,
    analytics,
    predictions,
    recommendations,
    simulations,
    ai_assistant,
    smart_features,
)
from app.services.gemini_ai import get_ai_configuration_status
from app.utils.seed_demo import seed_demo_data

# Configure structured diagnostic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [FinPilot-AI] %(message)s",
)
logger = logging.getLogger("finpilot")

# Resolve absolute project and frontend directories deterministically
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

FRONTEND_HTML_FILES = [
    "index.html",
    "dashboard.html",
    "transactions.html",
    "analytics.html",
    "predictions.html",
    "recommendations.html",
    "simulations.html",
    "assistant.html",
]

FRONTEND_PAGES = {name.replace(".html", "") for name in FRONTEND_HTML_FILES}


def log_startup_diagnostics():
    """Print and verify FRONTEND_DIR, static assets, module location, and AI configuration status."""
    logger.info("=" * 72)
    logger.info("FinPilot AI Startup Diagnostics")
    logger.info("Module file     : %s", Path(__file__).resolve())
    logger.info("Project root    : %s", PROJECT_ROOT)
    logger.info("FRONTEND_DIR    : %s (exists=%s)", FRONTEND_DIR, FRONTEND_DIR.exists())

    required_assets = [
        "index.html",
        "dashboard.html",
        "transactions.html",
        "analytics.html",
        "predictions.html",
        "recommendations.html",
        "simulations.html",
        "assistant.html",
        "css/style.css",
        "js/app.js",
    ]
    missing_assets = []
    for rel_path in required_assets:
        asset_path = FRONTEND_DIR / rel_path
        if not asset_path.exists():
            missing_assets.append(rel_path)

    if missing_assets:
        logger.warning("Missing frontend assets: %s", ", ".join(missing_assets))
    else:
        logger.info("Verified all %d frontend HTML/CSS/JS entry assets exist.", len(required_assets))

    ai_status = get_ai_configuration_status()
    logger.info(
        "Gemini AI status: configured=%s | model=%s",
        ai_status.get("ai_configured"),
        ai_status.get("model"),
    )
    logger.info("=" * 72)


def initialize_database_and_demo():
    """Ensure database tables exist and seed initial demo data only if the database is empty."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        tx_count = db.query(Transaction).count()
        if tx_count == 0:
            logger.info("Database is empty — seeding initial INR demo dataset...")
            seed_demo_data(db, reset_existing_demo=False)
        else:
            logger.info("Database verified: %d existing transactions preserved.", tx_count)
    except Exception as exc:
        logger.warning("Demo seeding check skipped: %s", exc)
    finally:
        db.close()


# Ensure tables exist and diagnostics print when imported by ASGI workers
initialize_database_and_demo()
log_startup_diagnostics()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify database initialization and frontend paths on FastAPI startup."""
    initialize_database_and_demo()
    log_startup_diagnostics()
    yield


app = FastAPI(
    title="FinPilot AI – Personal Financial Operating System",
    description=(
        "AI-powered financial management, automated transaction categorization, "
        "recurring payment detection, hybrid time-series cash flow forecasting, "
        "anomaly detection, personalized recommendations, financial simulations, "
        "and Google Gemini AI financial assistant."
    ),
    version="1.1.0",
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


# Safe Global Exception Handlers (never expose internal stack traces or secrets)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        loc = " -> ".join(str(x) for x in err.get("loc", []) if x != "body")
        msg = err.get("msg", "Invalid input")
        errors.append(f"{loc}: {msg}" if loc else msg)
    logger.warning("Validation error on %s %s: %s", request.method, request.url.path, errors)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "validation_error",
            "detail": "; ".join(errors) if errors else "Invalid request parameters.",
            "errors": errors,
        },
    )


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        logger.warning(
            "404 Not Found: %s %s (FRONTEND_DIR=%s)",
            request.method,
            request.url.path,
            FRONTEND_DIR,
        )
        # Always return JSON for API requests or when JSON is explicitly preferred
        accept_header = request.headers.get("accept", "")
        if request.url.path.startswith("/api/") or "text/html" not in accept_header:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={
                    "status": "not_found",
                    "detail": f"Route '{request.url.path}' was not found on FinPilot AI.",
                    "path": request.url.path,
                    "available_pages": [
                        "/",
                        "/dashboard.html",
                        "/transactions.html",
                        "/analytics.html",
                        "/predictions.html",
                        "/recommendations.html",
                        "/simulations.html",
                        "/assistant.html",
                    ],
                },
            )
        # Styled HTML 404 response for browser navigation
        return HTMLResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>404 Page Not Found – FinPilot AI</title>
  <link rel="stylesheet" href="/css/style.css" />
</head>
<body style="display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px;background:#070B14;color:#F8FAFC;font-family:sans-serif;">
  <div style="max-width:520px;background:#0F172A;border:1px solid rgba(148,163,184,0.16);border-radius:16px;padding:36px;text-align:center;">
    <div style="font-size:2.5rem;font-weight:800;color:#6366F1;margin-bottom:8px;">404</div>
    <h1 style="font-size:1.35rem;margin-bottom:10px;">Page Not Found</h1>
    <p style="color:#94A3B8;font-size:0.92rem;margin-bottom:24px;">
      The requested URL <code>{request.url.path}</code> does not exist on FinPilot AI.
    </p>
    <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
      <a href="/dashboard.html" class="btn btn-primary" style="text-decoration:none;padding:10px 18px;border-radius:10px;background:#4F46E5;color:#fff;font-weight:600;">Go to Dashboard</a>
      <a href="/" class="btn btn-secondary" style="text-decoration:none;padding:10px 18px;border-radius:10px;background:#1E293B;color:#E2E8F0;font-weight:600;">Home</a>
    </div>
  </div>
</body>
</html>""",
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "detail": str(exc.detail),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "detail": "An unexpected server error occurred while processing your request. Please verify your input and try again.",
        },
    )


# ============================================================================
# 1. API ROUTES (Registered First so Static Routes Never Shadow /api/*)
# ============================================================================

@app.get("/api/health", tags=["System"], status_code=status.HTTP_200_OK)
def health_check():
    """Return system health, database status, AI configuration status, and active timestamp."""
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

    ai_info = get_ai_configuration_status()

    return {
        "status": "healthy",
        "service": "FinPilot AI Backend",
        "version": "1.1.0",
        "database": db_status,
        "transactions_count": total_tx,
        "demo_transactions_count": demo_tx,
        "user_transactions_count": user_tx,
        "ai_configured": ai_info.get("ai_configured", False),
        "ai_model": ai_info.get("model"),
        "frontend_dir_exists": FRONTEND_DIR.exists(),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


app.include_router(transactions.router)
app.include_router(analytics.router)
app.include_router(predictions.router)
app.include_router(recommendations.router)
app.include_router(simulations.router)
app.include_router(ai_assistant.router)
app.include_router(smart_features.router)


# ============================================================================
# 2. STATIC ASSETS & FRONTEND HTML ROUTES
# ============================================================================

def _serve_frontend_file(filename: str) -> FileResponse:
    """Resolve and return a file inside FRONTEND_DIR or raise 404 with diagnostic logging."""
    target = (FRONTEND_DIR / filename).resolve()
    if not str(target).startswith(str(FRONTEND_DIR.resolve())) or not target.is_file():
        logger.warning("Frontend file missing: %s (expected at %s)", filename, target)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Frontend file '{filename}' not found.",
        )
    media_type = "text/html"
    if filename.endswith(".css"):
        media_type = "text/css"
    elif filename.endswith(".js"):
        media_type = "application/javascript"
    return FileResponse(str(target), media_type=media_type)


# Mount /css and /js static directories when present
if (FRONTEND_DIR / "css").is_dir():
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")

if (FRONTEND_DIR / "js").is_dir():
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")


@app.get("/", include_in_schema=False)
def serve_root():
    return _serve_frontend_file("index.html")


@app.get("/index.html", include_in_schema=False)
def serve_index_html():
    return _serve_frontend_file("index.html")


@app.get("/dashboard.html", include_in_schema=False)
def serve_dashboard_html():
    return _serve_frontend_file("dashboard.html")


@app.get("/transactions.html", include_in_schema=False)
def serve_transactions_html():
    return _serve_frontend_file("transactions.html")


@app.get("/analytics.html", include_in_schema=False)
def serve_analytics_html():
    return _serve_frontend_file("analytics.html")


@app.get("/predictions.html", include_in_schema=False)
def serve_predictions_html():
    return _serve_frontend_file("predictions.html")


@app.get("/recommendations.html", include_in_schema=False)
def serve_recommendations_html():
    return _serve_frontend_file("recommendations.html")


@app.get("/simulations.html", include_in_schema=False)
def serve_simulations_html():
    return _serve_frontend_file("simulations.html")


@app.get("/assistant.html", include_in_schema=False)
def serve_assistant_html():
    return _serve_frontend_file("assistant.html")


@app.get("/{page_name}.html", include_in_schema=False)
def serve_any_known_html(page_name: str):
    if page_name in FRONTEND_PAGES:
        return _serve_frontend_file(f"{page_name}.html")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Page '{page_name}.html' not found")


@app.get("/{page_name}", include_in_schema=False)
def serve_clean_page_route(page_name: str):
    if page_name in FRONTEND_PAGES:
        return _serve_frontend_file(f"{page_name}.html")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Route '/{page_name}' not found")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
