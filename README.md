# FinPilot AI – Personal Financial Operating System

**FinPilot AI** is a full-stack, AI-powered financial management and decision intelligence platform designed for individuals and small businesses. It automates transaction categorization, detects recurring obligations (subscriptions, bills, regular income, and EMIs), forecasts 7-day, 30-day, and 90-day cash flows with statistical uncertainty bands, audits its own prediction accuracy, flags spending anomalies, generates data-backed saving recommendations, and simulates what-if financial decisions.

---

## 1. Technology Stack

### Backend
- **Language**: Python 3.11+
- **Web Framework**: FastAPI + Uvicorn (ASGI)
- **Database & ORM**: SQLite (WAL mode) + SQLAlchemy 2.x
- **Data Validation**: Pydantic v2
- **AI / ML & Data Science**: Scikit-Learn (`Ridge`, `IsolationForest`, `TfidfVectorizer`, `LogisticRegression`, `StandardScaler`), Pandas, NumPy

### Frontend
- **Structure & Styling**: Semantic HTML5 + Custom CSS3 (Dark Navy & Electric Blue Fintech Design System)
- **Interactivity**: Vanilla JavaScript (ES6+ Fetch API, Modals, Live Categorization, CSV Import/Export)
- **Visualizations**: Chart.js 4.x

---

## 2. Project Folder Structure

```text
FinPilot-AI/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI entrypoint, CORS, exception handling & static routing
│   │   ├── database.py              # SQLite engine, WAL configuration & SQLAlchemy session management
│   │   ├── models.py                # ORM tables: Transactions, RecurringPayments, FinancialBudgets, Predictions, Simulations
│   │   ├── schemas.py               # Strict Pydantic v2 request/response validation schemas
│   │   ├── routes/
│   │   │   ├── transactions.py      # CRUD, filtering, live AI categorization preview & CSV import
│   │   │   ├── analytics.py         # KPI summary, monthly trends, category matrix & recurring endpoint
│   │   │   ├── predictions.py       # 7D/30D/90D cash flow forecasts, accuracy evaluation & anomalies
│   │   │   ├── recommendations.py   # AI saving recommendations, excessive spend & budget customization
│   │   │   └── simulations.py       # What-if scenario engine & saved simulations management
│   │   ├── services/
│   │   │   ├── categorization.py    # Explainable Rule-Based + TF-IDF Logistic Regression Categorizer
│   │   │   ├── recurring.py         # Interval regularity & coefficient-of-variation recurring detector
│   │   │   ├── forecasting.py       # Hybrid Recurring-Schedule + Ridge Regression forecaster & MAE/MAPE backtester
│   │   │   ├── anomaly.py           # Isolation Forest, Category Z-Score & 3-day velocity spike detector
│   │   │   ├── recommendations.py   # Adaptive 50/30/20 budgets, saving opportunities & explainable AI insights
│   │   │   └── simulation.py        # Amortization EMI & multi-month cash flow impact simulator
│   │   └── utils/
│   │       └── seed_demo.py         # Indian Rupee (₹) demo data seeding & cleanup utility (`is_demo=True`)
│   └── requirements.txt
├── frontend/
│   ├── index.html                   # Overview Home & Live Portfolio Launchpad
│   ├── dashboard.html               # 10-Component Executive Financial Dashboard
│   ├── transactions.html            # Transaction Ledger, Live AI Categorizer & Bulk CSV Import/Export
│   ├── analytics.html               # Deep Financial Analytics & Recurring Payments Registry
│   ├── predictions.html             # 7D/30D/90D Cash Flow Forecasts, Accuracy Audit & Anomaly Center
│   ├── recommendations.html         # AI Saving Opportunities & Customizable Category Budgets
│   ├── simulations.html             # Interactive What-If Financial Decision Simulator
│   ├── css/
│   │   └── style.css                # Responsive Dark Navy & Electric Blue Fintech stylesheet
│   └── js/
│       ├── app.js                   # API client, INR formatters, toast notifications & shared shell
│       ├── dashboard.js             # Dashboard KPIs, charts, insights & quick-add controller
│       ├── transactions.js          # CRUD, multi-filter, CSV import/export & live AI preview
│       ├── analytics.js             # Trend charts, MoM category matrix & recurring stream filters
│       ├── predictions.js           # Multi-horizon forecast chart, backtest metrics & anomaly feed
│       ├── recommendations.js       # Saving cards, budget utilization bars & limit editor
│       └── simulations.js           # Scenario presets, trajectory comparison chart & schedule table
└── README.md
```

---

## 3. Core AI & Financial Engineering Features

1. **Explainable Automatic Categorization (`categorization.py`)**
   - Automatically classifies transactions into 12 categories: `Food`, `Shopping`, `Transportation`, `Healthcare`, `Entertainment`, `Education`, `Rent`, `Utilities`, `EMI and Loans`, `Salary`, `Freelance Income`, and `Other`.
   - Uses a deterministic Indian & global merchant keyword rule engine first, falling back to a `TfidfVectorizer + LogisticRegression` machine learning pipeline trained on stored history, and records a human-readable explanation for every classification.

2. **Recurring Payment & Subscription Detection (`recurring.py`)**
   - Clusters normalized merchant names, measures median inter-payment intervals (`Weekly`, `Bi-Weekly`, `Monthly`, `Quarterly`) and amount coefficient of variation ($\text{CV} = \sigma / \mu$), classifies streams into `Subscription`, `Recurring Bill`, `EMI Payment`, or `Regular Income`, and estimates the next due date.

3. **Hybrid Cash Flow Forecasting & Uncertainty Cones (`forecasting.py`)**
   - Decomposes future cash flows into deterministic **Scheduled Recurring Commitments** mapped to exact cycle dates and **Discretionary Daily Cash Flows** modeled via Scikit-Learn `Ridge` regression with cyclical day-of-week and day-of-month Fourier features ($\sin/\cos$).
   - Computes 7-day, 30-day, and 90-day projections with $\pm z \cdot \sigma \sqrt{t}$ uncertainty cones and flags insufficient historical data (`< 14 days`).

4. **Prediction Accuracy & Walk-Forward Backtesting (`forecasting.py`)**
   - Evaluates stored predictions and chronological out-of-sample walk-forward splits against realized transactions using **MAE** (Mean Absolute Error in ₹), **RMSE**, **MAPE** (Mean Absolute Percentage Error), and confidence band coverage. Refuses to fabricate accuracy scores when `< 30 days` of data exist.

5. **Statistical & ML Anomaly Detection (`anomaly.py`)**
   - Combines Category Z-Score / IQR thresholds and `IsolationForest` to flag **Unusually High Expenses**, and a rolling 3-day velocity detector to flag **Unusual Spending Frequency** bursts.

6. **Personalized Budgets, Recommendations & Simulations (`recommendations.py`, `simulation.py`)**
   - Generates adaptive monthly category spending limits (`FinancialBudgets`), quantifies monthly rupee savings opportunities, warns of upcoming bills within 14 days, and simulates 5 scenario types (`large_purchase`, `monthly_emi`, `loan_repayment`, `savings_target`, `additional_expense`).

---

## 4. REST API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | System & SQLite health status with demo/user record counts |
| `GET` | `/api/transactions` | List transactions with search, type, category, date & source filters |
| `POST` | `/api/transactions` | Create transaction with automatic AI categorization |
| `PUT` | `/api/transactions/{id}` | Edit an existing transaction |
| `DELETE` | `/api/transactions/{id}` | Delete a transaction by ID |
| `POST` | `/api/transactions/import` | Bulk import transactions via CSV file upload or CSV text |
| `POST` | `/api/transactions/categorize-preview` | Live preview of AI category & explanation for a description |
| `POST` | `/api/transactions/seed-demo` | Seed/reset realistic Indian Rupee (₹) demo data (`is_demo=True`) |
| `DELETE` | `/api/transactions/demo` | Clear demo data while preserving user-entered transactions |
| `GET` | `/api/analytics/summary` | Portfolio totals, MoM deltas, monthly trends & AI insights |
| `GET` | `/api/analytics/categories` | Category-level expense/income totals, shares & MoM changes |
| `GET` | `/api/recurring` | Detected subscriptions, bills, regular income & EMIs |
| `GET` | `/api/predictions/cashflow` | 7-day, 30-day & 90-day cash flow forecasts with confidence bands |
| `GET` | `/api/predictions/accuracy` | Out-of-sample MAE, RMSE, MAPE & predicted-vs-actual checkpoints |
| `GET` | `/api/anomalies` | Flagged high-amount and high-frequency spending anomalies |
| `GET` | `/api/recommendations` | Personalized budgets, saving opportunities & payment warnings |
| `PUT` | `/api/recommendations/budgets` | Customize a monthly category spending limit |
| `POST` | `/api/simulations` | Run and save a what-if financial decision simulation |
| `GET` | `/api/simulations` | Retrieve all saved financial simulations |
| `DELETE` | `/api/simulations/{id}` | Delete a saved simulation by ID |

---

## 5. Installation & Execution Instructions

### Step 1: Set Up Python Virtual Environment & Install Dependencies
From the root `FinPilot-AI/` directory:

```powershell
# Create virtual environment
python -m venv .venv

# Install backend dependencies
.venv\Scripts\pip install -r backend/requirements.txt
```

### Step 2: Seed Realistic Indian Rupee (₹) Demo Data (Optional – Also Runs Automatically on Empty DB)
```powershell
cd backend
..\.venv\Scripts\python -m app.utils.seed_demo
```

### Step 3: Start the FastAPI Backend Server
From the `backend/` directory:

```powershell
cd backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- **API Base URL**: `http://127.0.0.1:8000`
- **Interactive Swagger API Docs**: `http://127.0.0.1:8000/docs`

### Step 4: Run the Frontend Web Server
You can either access the frontend directly through the FastAPI server at `http://127.0.0.1:8000/dashboard.html` OR run a dedicated local web server in the `frontend/` directory:

```powershell
cd frontend
..\.venv\Scripts\python -m http.server 3000
```
Then open **`http://localhost:3000/dashboard.html`** (or `http://localhost:3000/index.html`) in your browser.

---

## 6. Production Deployment on Render

FinPilot AI is pre-configured for one-click cloud deployment on **Render** via [`render.yaml`](render.yaml), where FastAPI serves both the REST APIs (`/api/*`) and the complete HTML/CSS/JS frontend from the same domain.

- **Build Command**: `pip install -r backend/requirements.txt`
- **Start Command**: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Health Check Endpoint**: `/api/health`

