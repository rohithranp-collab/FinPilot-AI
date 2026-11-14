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
let monthlyIncomeExpenseChartInstance = null;
let healthSpeedometerChartInstance = null;
let cachedForecastData = null;
let cachedSmartBundle = null;
let activeHorizonDays = 30;
let activeOperatingMode = 'individual';
let isStressTestActive = false;

async function loadDashboardData() {
  try {
    await refreshSidebarStatus();
    const [summary, categories, forecast, txData, recurring, anomalies, smart] = await Promise.all([
      apiRequest('/api/analytics/summary'),
      apiRequest('/api/analytics/categories'),
      apiRequest('/api/predictions/cashflow?horizon=90'),
      apiRequest('/api/transactions?limit=8'),
      apiRequest('/api/recurring'),
      apiRequest('/api/anomalies'),
      apiRequest(`/api/smart/overview?stress_test=${isStressTestActive}`),
    ]);

    cachedForecastData = forecast;
    cachedSmartBundle = smart;

    renderDashboardKPIs(summary, forecast);
    renderCashflowForecastChart(forecast, activeHorizonDays);
    renderExpenseCategoryChart(categories);
    renderMonthlyIncomeExpenseChart(summary.monthly_trends || []);
    renderRecentTransactions(txData.transactions || []);
    renderUpcomingRecurring(recurring.recurring_payments || [], recurring.summary || {});
    renderUnusualSpendingAlerts(smart.anomaly_stories || anomalies.anomalies || [], anomalies.summary || {});
    renderAIFinancialInsights(summary.ai_insights || []);

    // Render 12 Smart Financial OS Hackathon Suite Components
    renderHealthSpeedometer1000(smart.health_score_1000);
    renderSubscriptionKiller(smart.subscription_killer);
    renderExplainableShapAndMonteCarlo(smart.explainable_ai, smart.income_uncertainty);
    renderLiquidityPanicBanner(smart.liquidity_panic);
    renderSmallBusinessGstPanel(smart.small_business_gst);
    renderFestivalAdaptiveBanner(smart.festival_budgets);
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

function renderMonthlyIncomeExpenseChart(monthlyTrends) {
  const canvas = document.getElementById('monthlyIncomeExpenseChart');
  if (!canvas || typeof Chart === 'undefined') return;

  if (monthlyIncomeExpenseChartInstance) {
    monthlyIncomeExpenseChartInstance.destroy();
  }

  if (!monthlyTrends || !monthlyTrends.length) return;

  const ctx = canvas.getContext('2d');
  monthlyIncomeExpenseChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: monthlyTrends.map((m) => m.month),
      datasets: [
        {
          label: 'Monthly Income',
          data: monthlyTrends.map((m) => m.income),
          backgroundColor: 'rgba(16, 185, 129, 0.78)',
          borderColor: '#10b981',
          borderWidth: 1,
          borderRadius: 6,
        },
        {
          label: 'Monthly Expenses',
          data: monthlyTrends.map((m) => m.expenses),
          backgroundColor: 'rgba(244, 63, 94, 0.78)',
          borderColor: '#f43f5e',
          borderWidth: 1,
          borderRadius: 6,
        },
        {
          type: 'line',
          label: 'Net Monthly Savings',
          data: monthlyTrends.map((m) => m.savings),
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56, 189, 248, 0.15)',
          borderWidth: 2.5,
          pointRadius: 3,
          tension: 0.3,
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
            label: (ctx) => `${ctx.dataset.label}: ${formatINR(ctx.raw)}`,
          },
        },
      },
      scales: {
        y: {
          ticks: {
            callback: (val) => formatCompactINR(val),
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
    countBadge.textContent = `${anomalies.length} Story Alerts`;
  }
  if (!container) return;

  if (!anomalies.length) {
    container.innerHTML = `<div class="empty-state"><p>No unusual spending anomalies detected in your recent history.</p></div>`;
    return;
  }

  container.innerHTML = anomalies
    .slice(0, 4)
    .map(
      (a, idx) => `
    <div class="insight-item ${a.severity === 'High' ? 'danger' : 'warning'}" id="anomalyStoryCard_${idx}">
      <div class="insight-body">
        <h4>
          📖 ${escapeHtml(a.description)}
          <span class="badge ${a.severity === 'High' ? 'badge-danger' : 'badge-warning'}" style="margin-left:6px;">
            ${escapeHtml(a.anomaly_type)}
          </span>
        </h4>
        <p>${escapeHtml(a.story_narrative || a.explanation)}</p>
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-top:8px;">
          <span style="font-size:0.74rem;color:var(--text-muted);">
            ${formatDate(a.date)} • ${escapeHtml(a.category)} • ${escapeHtml(a.detection_method)}
          </span>
          <div style="display:flex;gap:6px;" id="anomalyActionBtns_${idx}">
            <button type="button" class="btn btn-secondary btn-xs" onclick="acknowledgeAnomalyStory(${idx}, true)">✓ Yes, Planned Party/Event</button>
            <button type="button" class="btn btn-danger btn-xs" onclick="acknowledgeAnomalyStory(${idx}, false)">⚑ Keep Flagged</button>
          </div>
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

function acknowledgeAnomalyStory(idx, isPlanned) {
  const btnGroup = document.getElementById(`anomalyActionBtns_${idx}`);
  const card = document.getElementById(`anomalyStoryCard_${idx}`);
  if (btnGroup) {
    btnGroup.innerHTML = isPlanned
      ? `<span class="badge badge-success">✓ Marked as Planned Celebration</span>`
      : `<span class="badge badge-danger">⚑ Flagged for Budget Watch</span>`;
  }
  if (card && isPlanned) {
    card.className = 'insight-item positive';
  }
  showToast(
    isPlanned
      ? 'Got it! AI Story Mode marked this spike as a planned celebration.'
      : 'Kept flagged in your budget watch list.',
    'info'
  );
}

/**
 * Feature #9: CIBIL-Style 0-1000 Financial Health Speedometer
 */
function renderHealthSpeedometer1000(scoreObj) {
  if (!scoreObj) return;
  const valEl = document.getElementById('score1000BigValue');
  const tierEl = document.getElementById('score1000TierBadge');
  const pillarsEl = document.getElementById('score1000PillarsList');
  const tipsEl = document.getElementById('score1000BoostTips');

  if (valEl) {
    valEl.textContent = scoreObj.score_1000;
    valEl.style.color = scoreObj.color || '#10b981';
  }
  if (tierEl) {
    tierEl.textContent = `${scoreObj.score_1000}/1000 • ${scoreObj.tier}`;
  }

  const canvas = document.getElementById('healthSpeedometerChart');
  if (canvas && typeof Chart !== 'undefined') {
    if (healthSpeedometerChartInstance) {
      healthSpeedometerChartInstance.destroy();
    }
    const score = scoreObj.score_1000 || 750;
    const rem = Math.max(0, 1000 - score);
    healthSpeedometerChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: ['FinPilot Score', 'Remaining'],
        datasets: [
          {
            data: [score, rem],
            backgroundColor: [scoreObj.color || '#10b981', 'rgba(148, 163, 184, 0.14)'],
            borderWidth: 0,
            circumference: 180,
            rotation: 270,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '76%',
        plugins: {
          legend: { display: false },
          tooltip: { enabled: false },
        },
      },
    });
  }

  if (pillarsEl && scoreObj.pillars) {
    const pList = Object.values(scoreObj.pillars);
    pillarsEl.innerHTML = pList
      .map((p) => {
        const pct = Math.round((p.points / p.max) * 100);
        return `
        <div>
          <div style="display:flex;justify-content:space-between;font-size:0.78rem;margin-bottom:2px;">
            <span>${escapeHtml(p.label)}</span>
            <strong class="amount-cell">${p.points} / ${p.max} pts</strong>
          </div>
          <div class="progress-track" style="height:6px;margin:3px 0;">
            <div class="progress-fill" style="width:${pct}%;"></div>
          </div>
        </div>
      `;
      })
      .join('');
  }

  if (tipsEl && Array.isArray(scoreObj.score_boost_tips)) {
    tipsEl.innerHTML = `
      <div style="font-size:0.78rem;font-weight:700;color:#93c5fd;margin-bottom:4px;">🚀 How to Boost Your Score to 850+:</div>
      ${scoreObj.score_boost_tips
        .map((t) => `<div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:2px;">• ${escapeHtml(t)}</div>`)
        .join('')}
    `;
  }
}

/**
 * Feature #1: Auto-Subscription Killer & Price Hike Detector
 */
function renderSubscriptionKiller(subKiller) {
  const container = document.getElementById('subscriptionKillerContainer');
  const badgeEl = document.getElementById('subWasteAnnualBadge');
  if (!container || !subKiller) return;

  if (badgeEl) {
    badgeEl.textContent = `${formatINR(subKiller.total_annual_waste || 0)}/yr Recoverable`;
  }

  const hikes = subKiller.price_hikes || [];
  const candidates = subKiller.cancel_candidates || [];

  let html = '';
  hikes.forEach((h) => {
    html += `
      <div class="insight-item danger" style="padding:11px 14px;">
        <div class="insight-body">
          <h4>📈 Price Hike Alert: ${escapeHtml(h.name)} <span class="badge badge-danger">+${h.increase_percent}%</span></h4>
          <p>${escapeHtml(h.alert_message)}</p>
        </div>
        <div class="insight-impact" style="background:var(--danger-bg);color:#fb7185;">
          +${formatINR(h.annual_extra_cost)}/yr
        </div>
      </div>
    `;
  });

  candidates.slice(0, 4).forEach((c) => {
    html += `
      <div class="insight-item warning" style="padding:11px 14px;" id="subCancelCard_${c.id}">
        <div class="insight-body">
          <h4>
            ✂️ ${escapeHtml(c.name)}
            <span class="badge badge-neutral" style="margin-left:6px;">${formatINR(c.monthly_amount)}/mo</span>
          </h4>
          <p>${escapeHtml(c.usage_status)} • Saves <strong>${formatINR(c.annual_waste)}/year</strong></p>
        </div>
        <div>
          <button type="button" class="btn btn-danger btn-xs" onclick="cancelSubscriptionOneClick(${c.id}, '${escapeHtml(c.name).replace(/'/g, "\\'")}')">
            Cancel in 1 Click
          </button>
        </div>
      </div>
    `;
  });

  if (!html) {
    html = `<div class="empty-state"><p>All active subscriptions are optimized with no price hikes detected.</p></div>`;
  }
  container.innerHTML = html;
}

async function cancelSubscriptionOneClick(subId, subName) {
  try {
    const res = await apiRequest(`/api/smart/cancel-subscription/${subId}`, { method: 'POST' });
    showToast(res.message, 'success');
    const card = document.getElementById(`subCancelCard_${subId}`);
    if (card) {
      card.className = 'insight-item positive';
      card.innerHTML = `
        <div class="insight-body">
          <h4>✅ Cancelled: ${escapeHtml(subName)}</h4>
          <p>${escapeHtml(res.message)}</p>
        </div>
        <span class="badge badge-success">Saved ${formatINR(res.annual_saved)}/yr</span>
      `;
    }
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/**
 * Feature #5 & #3: Explainable AI (SHAP Attribution %) + Salary/Freelance Monte Carlo Engine
 */
function renderExplainableShapAndMonteCarlo(shapObj, mcObj) {
  const shapSummaryEl = document.getElementById('shapHumanSummary');
  const shapListEl = document.getElementById('shapDriversList');
  const shapConfEl = document.getElementById('shapConfBadge');

  if (shapObj) {
    if (shapConfEl) {
      shapConfEl.textContent = `${shapObj.confidence_percent}% Confidence (${shapObj.confidence_level})`;
    }
    if (shapSummaryEl) {
      shapSummaryEl.innerHTML = `<strong>Why this forecast?</strong> ${escapeHtml(shapObj.human_explanation)}`;
    }
    if (shapListEl) {
      shapListEl.innerHTML = (shapObj.shap_drivers || [])
        .map(
          (d) => `
        <div style="background:rgba(10,18,38,0.6);padding:9px 12px;border-radius:8px;border:1px solid var(--border-subtle);">
          <div style="display:flex;justify-content:space-between;font-size:0.82rem;margin-bottom:4px;">
            <strong>${escapeHtml(d.feature)}</strong>
            <span class="amount-cell">${formatINR(d.monthly_rupee_impact)}/mo (<strong>${d.attribution_percent}% Impact</strong>)</span>
          </div>
          <div class="progress-track" style="height:6px;margin:4px 0;">
            <div class="progress-fill warning" style="width:${Math.min(100, d.attribution_percent)}%;"></div>
          </div>
          <div style="font-size:0.75rem;color:var(--text-secondary);">${escapeHtml(d.explanation)}</div>
        </div>
      `
        )
        .join('');
    }
  }

  const mcContainer = document.getElementById('incomeUncertaintyContainer');
  const mcBadge = document.getElementById('incomeVolatilityBadge');
  if (mcContainer && mcObj) {
    if (mcBadge) {
      mcBadge.textContent = mcObj.income_volatility_label || 'Monte Carlo';
    }
    mcContainer.innerHTML = `
      <div class="ai-preview-box" style="margin-top:0;margin-bottom:14px;">
        <strong>🎲 Probabilistic Income Forecast:</strong> ${escapeHtml(mcObj.narrative)}
      </div>
      <div class="grid-2" style="gap:12px;margin-bottom:12px;">
        <div style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.3);border-radius:10px;padding:12px;">
          <div style="font-size:0.75rem;color:var(--text-secondary);">ON-TIME SALARY (${escapeHtml(mcObj.expected_on_time_date || '5th')})</div>
          <div style="font-family:var(--font-mono);font-size:1.35rem;font-weight:800;color:#34d399;margin:4px 0;">
            ${mcObj.salary_on_time_probability}% Probability
          </div>
          <div style="font-size:0.78rem;color:var(--text-secondary);">Expected Credit: <strong>${formatINR(mcObj.expected_salary_amount)}</strong></div>
        </div>
        <div style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);border-radius:10px;padding:12px;">
          <div style="font-size:0.75rem;color:var(--text-secondary);">DELAY RISK (TILL ${escapeHtml(mcObj.expected_delayed_date || '10th')})</div>
          <div style="font-family:var(--font-mono);font-size:1.35rem;font-weight:800;color:#fbbf24;margin:4px 0;">
            ${mcObj.salary_delay_probability}% Probability
          </div>
          <div style="font-size:0.78rem;color:var(--text-secondary);">Freelance 30D Chance: <strong>${mcObj.freelance_probability_30d}%</strong></div>
        </div>
      </div>
      <div style="display:flex;justify-content:space-between;background:rgba(10,18,38,0.65);padding:10px 14px;border-radius:8px;font-size:0.8rem;">
        <span>Freelance P10 (Conservative): <strong>${formatINR(mcObj.freelance_p10)}</strong></span>
        <span>Median P50: <strong style="color:#38bdf8;">${formatINR(mcObj.freelance_p50)}</strong></span>
        <span>Upside P90: <strong style="color:#34d399;">${formatINR(mcObj.freelance_p90)}</strong></span>
      </div>
    `;
  }
}

/**
 * Feature #6: Liquidity Panic Button + Auto Loan / Runway Saver
 */
function toggleLiquidityStressTest() {
  isStressTestActive = !isStressTestActive;
  const btn = document.getElementById('stressTestBtn');
  if (btn) {
    btn.textContent = isStressTestActive ? '✅ Exit Panic Sim' : '🚨 Panic Sim';
  }
  loadDashboardData();
}

function renderLiquidityPanicBanner(panicObj) {
  const section = document.getElementById('liquidityPanicSection');
  if (!section || !panicObj) return;

  if (!panicObj.is_panic_triggered) {
    section.style.display = 'none';
    return;
  }

  section.style.display = 'block';
  const actionsHtml = (panicObj.rescue_actions || [])
    .map(
      (a) => `
    <div style="background:rgba(15,23,42,0.88);border:1px solid rgba(244,63,94,0.4);border-radius:10px;padding:14px;display:flex;flex-direction:column;justify-content:space-between;gap:10px;">
      <div>
        <span class="badge badge-danger" style="margin-bottom:6px;">Option ${a.step}</span>
        <h4 style="font-size:0.92rem;margin-bottom:4px;">${escapeHtml(a.title)}</h4>
        <p style="font-size:0.8rem;color:var(--text-secondary);">${escapeHtml(a.description)}</p>
      </div>
      <button type="button" class="btn btn-primary btn-xs" onclick="showToast('Executed Rescue Action: ${escapeHtml(a.title)}', 'success')">
        ⚡ ${escapeHtml(a.button_label)}
      </button>
    </div>
  `
    )
    .join('');

  section.innerHTML = `
    <div class="card" style="margin-bottom:0;border:2px solid #f43f5e;background:linear-gradient(135deg, rgba(136, 19, 55, 0.35), rgba(15, 23, 42, 0.95));">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:14px;">
        <div>
          <span class="badge badge-danger">🚨 LIQUIDITY SHORTFALL ALERT (< 15 DAYS)</span>
          <h3 style="font-size:1.15rem;margin-top:6px;color:#fda4af;">Liquidity Panic Advisor & Auto-Runway Saver Activated</h3>
          <p style="font-size:0.86rem;color:#fecdd3;margin-top:2px;">${escapeHtml(panicObj.trigger_reason)}</p>
        </div>
        <button type="button" class="btn btn-secondary btn-sm" onclick="toggleLiquidityStressTest()">Dismiss Stress Simulation</button>
      </div>
      <div class="grid-3" style="margin-bottom:0;gap:14px;">
        ${actionsHtml}
      </div>
    </div>
  `;
}

/**
 * Feature #11: Small Business Mode Toggle (GST & Vendor Intelligence)
 */
function switchOperatingMode(mode) {
  activeOperatingMode = mode;
  const indBtn = document.getElementById('modeBtnIndividual');
  const bizBtn = document.getElementById('modeBtnBusiness');
  const bizSection = document.getElementById('smallBusinessGstSection');

  if (indBtn) indBtn.classList.toggle('active', mode === 'individual');
  if (bizBtn) bizBtn.classList.toggle('active', mode === 'business');

  if (bizSection) {
    bizSection.style.display = mode === 'business' ? 'block' : 'none';
  }
  if (mode === 'business' && cachedSmartBundle) {
    renderSmallBusinessGstPanel(cachedSmartBundle.small_business_gst);
    showToast('Switched to Small Business / MSME Mode (GST Input Tax Credit & Vendor Intelligence active)', 'info');
  }
}

function renderSmallBusinessGstPanel(gstObj) {
  const section = document.getElementById('smallBusinessGstSection');
  if (!section || !gstObj) return;
  section.style.display = activeOperatingMode === 'business' ? 'block' : 'none';

  const vendorsHtml = (gstObj.top_vendors || [])
    .map(
      (v) => `
    <span class="badge badge-neutral" style="padding:6px 10px;font-size:0.78rem;">
      ${escapeHtml(v.vendor)}: <strong>${formatINR(v.total_paid)}</strong>
    </span>
  `
    )
    .join('');

  section.innerHTML = `
    <div class="card" style="margin-bottom:0;border:1px solid rgba(56, 189, 248, 0.45);background:linear-gradient(135deg, rgba(12, 74, 110, 0.3), rgba(15, 23, 42, 0.92));">
      <div class="card-header" style="margin-bottom:14px;padding-bottom:10px;">
        <div>
          <div class="card-title">
            🏢 Small Business / MSME Mode — GST & Vendor Cashflow Intelligence
            <span class="badge badge-info">GSTR-1 in ${gstObj.gstr1_days_left}d • GSTR-3B in ${gstObj.gstr3b_days_left}d</span>
          </div>
          <div class="card-subtitle">Automated Input Tax Credit (ITC) tracking, vendor payouts & Accounting Profit vs Cashflow differential</div>
        </div>
      </div>
      <div class="kpi-grid" style="margin-bottom:14px;">
        <div class="kpi-card" style="padding:14px;">
          <div class="kpi-label">Claimable GST Input Credit (ITC)</div>
          <div class="kpi-value" style="font-size:1.35rem;color:#34d399;margin-top:4px;">${formatINR(gstObj.estimated_itc_claimable)}</div>
          <div style="font-size:0.74rem;color:var(--text-secondary);">18% ITC on ${formatINR(gstObj.gst_eligible_vendor_spend)} eligible spend</div>
        </div>
        <div class="kpi-card" style="padding:14px;">
          <div class="kpi-label">Estimated Output GST</div>
          <div class="kpi-value" style="font-size:1.35rem;color:#fbbf24;margin-top:4px;">${formatINR(gstObj.estimated_output_gst)}</div>
          <div style="font-size:0.74rem;color:var(--text-secondary);">Net GST Payable: <strong>${formatINR(gstObj.net_gst_payable)}</strong></div>
        </div>
        <div class="kpi-card" style="padding:14px;">
          <div class="kpi-label">Accounting Profit (P&L)</div>
          <div class="kpi-value" style="font-size:1.35rem;color:#38bdf8;margin-top:4px;">${formatINR(gstObj.accounting_profit_estimate)}</div>
          <div style="font-size:0.74rem;color:var(--text-secondary);">Excludes loan principal & adds ITC</div>
        </div>
        <div class="kpi-card" style="padding:14px;">
          <div class="kpi-label">Profit vs Cashflow Diff</div>
          <div class="kpi-value" style="font-size:1.35rem;color:#a78bfa;margin-top:4px;">+${formatINR(gstObj.profit_vs_cashflow_diff)}</div>
          <div style="font-size:0.74rem;color:var(--text-secondary);">Net Liquid Cashflow: ${formatINR(gstObj.net_cashflow)}</div>
        </div>
      </div>
      <div class="ai-preview-box" style="margin-bottom:10px;">
        <strong>💡 P&L Profit vs Cashflow Insight:</strong> ${escapeHtml(gstObj.profit_cashflow_explanation)}
      </div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:0.8rem;">
        <strong style="color:var(--text-secondary);">Top Recurring Vendors & Payees:</strong>
        ${vendorsHtml}
      </div>
    </div>
  `;
}

/**
 * Feature #12: Festival-Adaptive Cultural Budget Banner
 */
function renderFestivalAdaptiveBanner(festObj) {
  const banner = document.getElementById('festivalAdaptiveBanner');
  if (!banner || !festObj) return;

  const chips = (festObj.adapted_budgets || [])
    .slice(0, 3)
    .map(
      (b) => `
    <span class="badge badge-info" style="padding:5px 10px;">
      ${escapeHtml(b.category)}: ${formatINR(b.standard_limit)} → <strong>${formatINR(b.festival_adjusted_limit)} (+${b.boost_percent}%)</strong>
    </span>
  `
    )
    .join('');

  banner.innerHTML = `
    <div style="background:rgba(30, 58, 138, 0.25);border:1px solid rgba(99, 102, 241, 0.35);border-radius:12px;padding:12px 18px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
      <div style="font-size:0.83rem;">
        <span class="badge badge-warning" style="margin-right:8px;">🪔 Cultural Intelligence</span>
        <strong>${escapeHtml(festObj.active_festival_season)}:</strong>
        <span style="color:var(--text-secondary);">${escapeHtml(festObj.explanation)}</span>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        ${chips}
      </div>
    </div>
  `;
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
