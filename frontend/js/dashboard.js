/**
 * FinPilot AI – Dashboard Controller (dashboard.html & index.html)
 * Loads all 10 required dashboard components dynamically from live backend APIs:
 * 1. Total Balance
 * 2. Total Income
 * 3. Total Expenses
 * 4. Monthly Savings
 * 5. Cash Flow Forecast Chart (7D / 30D / 90D)
 * 6. Expense Category Chart
 * 7. Recent Transactions
 * 8. Upcoming Recurring Payments
 * 9. Unusual Spending Alerts
 * 10. AI Financial Insights
 */

let cashflowForecastChartInstance = null;
let expenseCategoryChartInstance = null;
let cachedForecastData = null;
let activeHorizonDays = 30;

async function loadDashboardData() {
  try {
    const [summary, categories, forecast, txData, recurring, anomalies] = await Promise.all([
      apiRequest('/api/analytics/summary'),
      apiRequest('/api/analytics/categories'),
      apiRequest('/api/predictions/cashflow?horizon=90'),
      apiRequest('/api/transactions?limit=8'),
      apiRequest('/api/recurring'),
      apiRequest('/api/anomalies'),
    ]);

    cachedForecastData = forecast;

    renderDashboardKPIs(summary, forecast);
    renderCashflowForecastChart(forecast, activeHorizonDays);
    renderExpenseCategoryChart(categories);
    renderRecentTransactions(txData.transactions || []);
    renderUpcomingRecurring(recurring.recurring_payments || [], recurring.summary || {});
    renderUnusualSpendingAlerts(anomalies.anomalies || [], anomalies.summary || {});
    renderAIFinancialInsights(summary.ai_insights || []);
  } catch (err) {
    showToast(`Error loading dashboard data: ${err.message}`, 'error');
  }
}

function renderDashboardKPIs(summary, forecast) {
  const balEl = document.getElementById('kpiTotalBalance');
  const incEl = document.getElementById('kpiTotalIncome');
  const expEl = document.getElementById('kpiTotalExpenses');
  const savEl = document.getElementById('kpiMonthlySavings');

  if (balEl) balEl.textContent = formatINR(summary.total_balance);
  if (incEl) incEl.textContent = formatINR(summary.total_income);
  if (expEl) expEl.textContent = formatINR(summary.total_expenses);
  if (savEl) savEl.textContent = formatINR(summary.monthly_savings);

  const healthSub = document.getElementById('kpiBalanceSub');
  if (healthSub) {
    const ds = summary.dataset_info || {};
    healthSub.innerHTML = `
      <span>Health Score: <strong>${summary.financial_health_score || 0}/100 (${escapeHtml(summary.health_label || 'N/A')})</strong></span>
      <span class="badge ${ds.is_demo_active ? 'badge-demo' : 'badge-user'}">${ds.total_count || 0} txns</span>
    `;
  }

  const cm = summary.current_month || {};
  const incSub = document.getElementById('kpiIncomeSub');
  if (incSub) {
    const sign = (cm.income_mom_percent || 0) >= 0 ? '+' : '';
    incSub.innerHTML = `
      <span>${escapeHtml(cm.month || 'Current Mo')}: <strong>${formatINR(cm.income || 0)}</strong></span>
      <span class="badge ${(cm.income_mom_percent || 0) >= 0 ? 'badge-success' : 'badge-warning'}">${sign}${cm.income_mom_percent || 0}% MoM</span>
    `;
  }

  const expSub = document.getElementById('kpiExpenseSub');
  if (expSub) {
    const sign = (cm.expense_mom_percent || 0) >= 0 ? '+' : '';
    expSub.innerHTML = `
      <span>${escapeHtml(cm.month || 'Current Mo')}: <strong>${formatINR(cm.expenses || 0)}</strong></span>
      <span class="badge ${(cm.expense_mom_percent || 0) > 10 ? 'badge-danger' : 'badge-info'}">${sign}${cm.expense_mom_percent || 0}% MoM</span>
    `;
  }

  const savSub = document.getElementById('kpiSavingsSub');
  if (savSub) {
    savSub.innerHTML = `
      <span>Avg Surplus: <strong>${formatINR(summary.average_monthly_savings || 0)}/mo</strong></span>
      <span class="badge ${(summary.savings_rate_percent || 0) >= 20 ? 'badge-success' : 'badge-warning'}">${summary.savings_rate_percent || 0}% Rate</span>
    `;
  }

  // Update Forecast Header Badges if present
  const confBadge = document.getElementById('forecastConfidenceBadge');
  if (confBadge && forecast) {
    const hKey = `${activeHorizonDays}_days`;
    const hObj = (forecast.horizons && forecast.horizons[hKey]) || {};
    confBadge.textContent = `Confidence: ${hObj.confidence_percent || Math.round((forecast.confidence_score || 0) * 100)}% (${forecast.confidence_level || 'N/A'})`;
  }
}

function switchDashboardForecastHorizon(days, btnEl) {
  activeHorizonDays = days;
  if (btnEl && btnEl.parentElement) {
    btnEl.parentElement.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
    btnEl.classList.add('active');
  }
  if (cachedForecastData) {
    renderCashflowForecastChart(cachedForecastData, days);
  }
}

function renderCashflowForecastChart(forecast, horizonDays = 30) {
  const canvas = document.getElementById('cashflowForecastChart');
  if (!canvas || typeof Chart === 'undefined') return;

  const histSeries = (forecast.historical_daily_series || []).slice(-15);
  const futSeries = (forecast.daily_series || []).slice(0, horizonDays);

  const labels = [
    ...histSeries.map((d) => formatDate(d.date)),
    ...futSeries.map((d) => formatDate(d.date)),
  ];

  const histLen = histSeries.length;
  const actualData = [
    ...histSeries.map((d) => d.actual_balance),
    ...Array(futSeries.length).fill(null),
  ];

  // Connect last historical point to first forecast point smoothly
  const lastActual = histLen > 0 ? histSeries[histLen - 1].actual_balance : forecast.current_balance;
  const predictedData = [
    ...Array(Math.max(0, histLen - 1)).fill(null),
    ...(histLen > 0 ? [lastActual] : []),
    ...futSeries.map((d) => d.predicted_balance),
  ];

  const upperBoundData = [
    ...Array(Math.max(0, histLen - 1)).fill(null),
    ...(histLen > 0 ? [lastActual] : []),
    ...futSeries.map((d) => d.upper_bound_balance),
  ];

  const lowerBoundData = [
    ...Array(Math.max(0, histLen - 1)).fill(null),
    ...(histLen > 0 ? [lastActual] : []),
    ...futSeries.map((d) => d.lower_bound_balance),
  ];

  if (cashflowForecastChartInstance) {
    cashflowForecastChartInstance.destroy();
  }

  const ctx = canvas.getContext('2d');
  cashflowForecastChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Historical Balance',
          data: actualData,
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56, 189, 248, 0.12)',
          borderWidth: 2.5,
          pointRadius: 2,
          tension: 0.32,
        },
        {
          label: `Predicted Balance (${horizonDays}D)`,
          data: predictedData,
          borderColor: '#10b981',
          backgroundColor: 'rgba(16, 185, 129, 0.1)',
          borderWidth: 2.5,
          borderDash: [6, 4],
          pointRadius: 2,
          tension: 0.32,
        },
        {
          label: 'Upper Confidence Bound',
          data: upperBoundData,
          borderColor: 'rgba(59, 130, 246, 0.25)',
          backgroundColor: 'rgba(59, 130, 246, 0.10)',
          borderWidth: 1,
          pointRadius: 0,
          fill: '+1',
          tension: 0.32,
        },
        {
          label: 'Lower Confidence Bound',
          data: lowerBoundData,
          borderColor: 'rgba(59, 130, 246, 0.25)',
          backgroundColor: 'transparent',
          borderWidth: 1,
          pointRadius: 0,
          tension: 0.32,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        tooltip: {
          callbacks: {
            label: (ctx) => {
              if (ctx.raw === null || ctx.raw === undefined) return null;
              return `${ctx.dataset.label}: ${formatINR(ctx.raw)}`;
            },
          },
        },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 9 } },
        y: {
          ticks: {
            callback: (val) => formatCompactINR(val),
          },
        },
      },
    },
  });

  // Update Forecast Horizon Summary Footer
  const summaryFooter = document.getElementById('forecastQuickSummary');
  if (summaryFooter && forecast.horizons) {
    const h = forecast.horizons[`${horizonDays}_days`] || {};
    summaryFooter.innerHTML = `
      <div style="display:flex;flex-wrap:wrap;gap:18px;justify-content:space-between;align-items:center;padding-top:12px;border-top:1px solid var(--border-subtle);font-size:0.82rem;">
        <span><strong>${horizonDays}-Day Projected Income:</strong> <span class="amount-income">${formatINR(h.predicted_income)}</span></span>
        <span><strong>Projected Expenses:</strong> <span class="amount-expense">${formatINR(h.predicted_expense)}</span></span>
        <span><strong>Projected Closing Balance:</strong> <strong style="color:#38bdf8;">${formatINR(h.predicted_balance)}</strong> (±${formatINR(h.uncertainty_margin)})</span>
        <span><strong>Confidence:</strong> <span class="badge badge-info">${h.confidence_percent || 0}%</span></span>
      </div>
    `;
  }
}

function renderExpenseCategoryChart(categoriesData) {
  const canvas = document.getElementById('expenseCategoryChart');
  if (!canvas || typeof Chart === 'undefined') return;

  const cats = (categoriesData.expense_categories || []).slice(0, 8);
  if (expenseCategoryChartInstance) {
    expenseCategoryChartInstance.destroy();
  }

  if (cats.length === 0) {
    return;
  }

  const ctx = canvas.getContext('2d');
  expenseCategoryChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: cats.map((c) => `${c.category} (${c.percentage_of_expenses}%)`),
      datasets: [
        {
          data: cats.map((c) => c.total_amount),
          backgroundColor: cats.map((c) => getCategoryColor(c.category)),
          borderColor: '#0b132b',
          borderWidth: 2,
          hoverOffset: 8,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '64%',
      plugins: {
        legend: {
          position: 'right',
          labels: { padding: 12, font: { size: 11.5 } },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.label}: ${formatINR(ctx.raw)}`,
          },
        },
      },
    },
  });
}

function renderRecentTransactions(transactions) {
  const tbody = document.getElementById('recentTransactionsBody');
  if (!tbody) return;

  if (!transactions.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No transactions recorded yet. Click "+ Add Transaction" or "Seed Demo Data".</td></tr>`;
    return;
  }

  tbody.innerHTML = transactions
    .map(
      (tx) => `
    <tr>
      <td>${formatDate(tx.date)}</td>
      <td>
        <div style="font-weight:600;">${escapeHtml(tx.description)}</div>
        <div style="font-size:0.74rem;color:var(--text-secondary);">
          ${escapeHtml(tx.payment_method)}
          <span class="badge ${tx.is_demo ? 'badge-demo' : 'badge-user'}" style="margin-left:4px;">${tx.is_demo ? 'Demo' : 'User'}</span>
        </div>
      </td>
      <td>
        <span class="badge badge-neutral" style="border-color:${getCategoryColor(tx.category)}55;color:#e2e8f0;">
          ${escapeHtml(tx.category)}
        </span>
      </td>
      <td><span class="badge ${tx.type === 'income' ? 'badge-income' : 'badge-expense'}">${tx.type.toUpperCase()}</span></td>
      <td class="amount-cell ${tx.type === 'income' ? 'amount-income' : 'amount-expense'}">
        ${tx.type === 'income' ? '+' : '-'}${formatINR(tx.amount)}
      </td>
    </tr>
  `
    )
    .join('');
}

function renderUpcomingRecurring(items, summary) {
  const container = document.getElementById('upcomingRecurringList');
  const badgeEl = document.getElementById('recurringTotalBadge');
  if (badgeEl && summary) {
    badgeEl.textContent = `${formatINR(summary.total_monthly_recurring_expense || 0)}/mo Outflow`;
  }
  if (!container) return;

  const expenseRecurring = items.filter((r) => r.type === 'expense' && r.status === 'Active').slice(0, 6);
  if (!expenseRecurring.length) {
    container.innerHTML = `<div class="empty-state"><p>No recurring subscriptions or bills detected yet.</p></div>`;
    return;
  }

  container.innerHTML = expenseRecurring
    .map((r) => {
      const dueLabel =
        r.days_until_due === 0
          ? 'Due Today'
          : r.days_until_due > 0
          ? `Due in ${r.days_until_due}d (${formatDate(r.next_payment_date)})`
          : `Cycle: ${formatDate(r.next_payment_date)}`;
      const badgeClass =
        r.days_until_due >= 0 && r.days_until_due <= 5
          ? 'badge-warning'
          : 'badge-info';
      return `
      <div class="insight-item" style="border-left-color:${getCategoryColor(r.category)};padding:12px 14px;">
        <div class="insight-body">
          <h4>${escapeHtml(r.name)} <span class="badge badge-neutral" style="margin-left:6px;">${escapeHtml(r.recurring_type)}</span></h4>
          <p>${escapeHtml(r.frequency)} • ${dueLabel} • Confidence: ${Math.round(r.confidence * 100)}%</p>
        </div>
        <div style="text-align:right;">
          <div class="amount-cell amount-expense">${formatINR(r.average_amount)}</div>
          <span class="badge ${badgeClass}" style="margin-top:4px;">${dueLabel.split('(')[0]}</span>
        </div>
      </div>
    `;
    })
    .join('');
}

function renderUnusualSpendingAlerts(anomalies, summary) {
  const container = document.getElementById('unusualSpendingList');
  const countBadge = document.getElementById('anomalyCountBadge');
  if (countBadge) {
    countBadge.textContent = `${anomalies.length} Flagged`;
  }
  if (!container) return;

  if (!anomalies.length) {
    container.innerHTML = `<div class="empty-state"><p>No unusual spending anomalies detected in your recent history.</p></div>`;
    return;
  }

  container.innerHTML = anomalies
    .slice(0, 4)
    .map(
      (a) => `
    <div class="insight-item ${a.severity === 'High' ? 'danger' : 'warning'}">
      <div class="insight-body">
        <h4>
          ${escapeHtml(a.description)}
          <span class="badge ${a.severity === 'High' ? 'badge-danger' : 'badge-warning'}" style="margin-left:6px;">
            ${escapeHtml(a.anomaly_type)}
          </span>
        </h4>
        <p>${escapeHtml(a.explanation)}</p>
        <div style="font-size:0.74rem;color:var(--text-muted);margin-top:4px;">
          ${formatDate(a.date)} • Category: ${escapeHtml(a.category)} • Method: ${escapeHtml(a.detection_method)}
        </div>
      </div>
      <div class="insight-impact" style="background:var(--danger-bg);color:#fb7185;">
        ${formatINR(a.amount)}
      </div>
    </div>
  `
    )
    .join('');
}

function renderAIFinancialInsights(insights) {
  const container = document.getElementById('aiInsightsList');
  if (!container) return;

  if (!insights.length) {
    container.innerHTML = `<div class="empty-state"><p>Add transactions to generate explainable AI insights.</p></div>`;
    return;
  }

  container.innerHTML = insights
    .map(
      (item) => `
    <div class="insight-item ${escapeHtml(item.type || 'info')}">
      <div class="insight-body">
        <h4>${escapeHtml(item.title)}</h4>
        <p>${escapeHtml(item.message)}</p>
      </div>
      <div class="insight-impact">${escapeHtml(item.impact || '')}</div>
    </div>
  `
    )
    .join('');
}

/**
 * Quick Add Transaction from Dashboard Modal
 */
async function submitDashboardQuickTransaction(event) {
  event.preventDefault();
  const dateVal = document.getElementById('quickTxDate').value;
  const amountVal = parseFloat(document.getElementById('quickTxAmount').value);
  const descVal = document.getElementById('quickTxDesc').value;
  const typeVal = document.getElementById('quickTxType').value;
  const catVal = document.getElementById('quickTxCategory').value;
  const methodVal = document.getElementById('quickTxMethod').value;

  try {
    const res = await apiRequest('/api/transactions', {
      method: 'POST',
      body: JSON.stringify({
        date: dateVal,
        amount: amountVal,
        description: descVal,
        type: typeVal,
        category: catVal === 'Auto' ? null : catVal,
        payment_method: methodVal,
        is_demo: false,
      }),
    });
    closeModal('quickAddTxModal');
    showToast(
      `Added: ${res.transaction.description} (${formatINR(res.transaction.amount)}) → ${res.transaction.category}`,
      'success'
    );
    event.target.reset();
    document.getElementById('quickTxDate').value = new Date().toISOString().slice(0, 10);
    await refreshSidebarStatus();
    await loadDashboardData();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function previewQuickCategorization() {
  const descEl = document.getElementById('quickTxDesc');
  const typeEl = document.getElementById('quickTxType');
  const previewEl = document.getElementById('quickAiPreview');
  if (!descEl || !previewEl) return;

  const desc = descEl.value.trim();
  if (desc.length < 2) {
    previewEl.textContent = 'AI Auto-Categorizer: Type a description (e.g. "Swiggy Dinner", "Uber Ride", "Monthly Salary") to preview automatic categorization.';
    return;
  }

  try {
    const res = await apiRequest('/api/transactions/categorize-preview', {
      method: 'POST',
      body: JSON.stringify({
        description: desc,
        type: typeEl ? typeEl.value : 'expense',
      }),
    });
    previewEl.innerHTML = `<strong>AI Predicted Category: ${escapeHtml(res.category)}</strong> — ${escapeHtml(res.reason)}`;
  } catch (_) {}
}

document.addEventListener('DOMContentLoaded', () => {
  const dateInput = document.getElementById('quickTxDate');
  if (dateInput && !dateInput.value) {
    dateInput.value = new Date().toISOString().slice(0, 10);
  }
  if (document.getElementById('kpiTotalBalance')) {
    loadDashboardData();
  }
});
