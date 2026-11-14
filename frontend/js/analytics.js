/**
 * FinPilot AI – Deep Analytics & Recurring Payments Controller (analytics.html)
 */

let monthlyTrendChartInstance = null;
let categoryPieChartInstance = null;
let categoryMomBarChartInstance = null;
let allRecurringStreams = [];

async function loadAnalyticsPage() {
  try {
    const [summary, categories, recurring] = await Promise.all([
      apiRequest('/api/analytics/summary'),
      apiRequest('/api/analytics/categories'),
      apiRequest('/api/recurring'),
    ]);

    allRecurringStreams = recurring.recurring_payments || [];

    renderAnalyticsKPIs(summary, recurring.summary || {});
    renderMonthlyTrendChart(summary.monthly_trends || []);
    renderCategoryCharts(categories);
    renderCategoryBreakdownTable(categories.expense_categories || [], categories.current_month, categories.previous_month);
    renderRecurringTable(allRecurringStreams, 'All');
  } catch (err) {
    showToast(`Failed to load analytics: ${err.message}`, 'error');
  }
}

function renderAnalyticsKPIs(summary, recSummary) {
  const savRateEl = document.getElementById('anSavingsRate');
  const recExpEl = document.getElementById('anRecurringExpense');
  const subsTotalEl = document.getElementById('anSubscriptionsTotal');
  const healthScoreEl = document.getElementById('anHealthScore');

  if (savRateEl) savRateEl.textContent = `${summary.savings_rate_percent || 0}%`;
  if (recExpEl) recExpEl.textContent = formatINR(recSummary.total_monthly_recurring_expense || 0);
  if (subsTotalEl) subsTotalEl.textContent = formatINR(recSummary.subscriptions_total || 0);
  if (healthScoreEl) {
    healthScoreEl.textContent = `${summary.financial_health_score || 0}/100`;
  }

  const sub1 = document.getElementById('anSavingsSub');
  if (sub1) {
    sub1.textContent = `Avg Monthly Surplus: ${formatINR(summary.average_monthly_savings || 0)}`;
  }
  const sub2 = document.getElementById('anRecurringSub');
  if (sub2) {
    sub2.textContent = `${recSummary.active_count || 0} active recurring commitments`;
  }
  const sub3 = document.getElementById('anSubsSub');
  if (sub3) {
    sub3.textContent = `EMIs: ${formatINR(recSummary.emi_total || 0)}/mo • Bills: ${formatINR(recSummary.bills_total || 0)}/mo`;
  }
  const sub4 = document.getElementById('anHealthSub');
  if (sub4) {
    sub4.textContent = `Rating: ${summary.health_label || 'N/A'}`;
  }
}

function renderMonthlyTrendChart(monthlyTrends) {
  const canvas = document.getElementById('monthlyTrendChart');
  if (!canvas || typeof Chart === 'undefined') return;

  if (monthlyTrendChartInstance) {
    monthlyTrendChartInstance.destroy();
  }

  const labels = monthlyTrends.map((m) => m.month);
  const incomeSeries = monthlyTrends.map((m) => m.income);
  const expenseSeries = monthlyTrends.map((m) => m.expenses);
  const savingsSeries = monthlyTrends.map((m) => m.savings);

  const ctx = canvas.getContext('2d');
  monthlyTrendChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Monthly Income',
          data: incomeSeries,
          backgroundColor: 'rgba(16, 185, 129, 0.78)',
          borderColor: '#10b981',
          borderWidth: 1,
          borderRadius: 6,
        },
        {
          label: 'Monthly Expenses',
          data: expenseSeries,
          backgroundColor: 'rgba(244, 63, 94, 0.78)',
          borderColor: '#f43f5e',
          borderWidth: 1,
          borderRadius: 6,
        },
        {
          type: 'line',
          label: 'Net Monthly Savings',
          data: savingsSeries,
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56, 189, 248, 0.18)',
          borderWidth: 3,
          pointRadius: 4,
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
          ticks: { callback: (v) => formatCompactINR(v) },
        },
      },
    },
  });
}

function renderCategoryCharts(categoriesData) {
  const expCats = categoriesData.expense_categories || [];

  // 1. Doughnut Share Chart
  const pieCanvas = document.getElementById('analyticsCategoryPieChart');
  if (pieCanvas && typeof Chart !== 'undefined') {
    if (categoryPieChartInstance) categoryPieChartInstance.destroy();
    categoryPieChartInstance = new Chart(pieCanvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: expCats.map((c) => `${c.category} (${c.percentage_of_expenses}%)`),
        datasets: [
          {
            data: expCats.map((c) => c.total_amount),
            backgroundColor: expCats.map((c) => getCategoryColor(c.category)),
            borderColor: '#0b132b',
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '62%',
        plugins: {
          legend: { position: 'right' },
          tooltip: {
            callbacks: { label: (ctx) => `${ctx.label}: ${formatINR(ctx.raw)}` },
          },
        },
      },
    });
  }

  // 2. Current Month vs Previous Month Bar Chart
  const barCanvas = document.getElementById('analyticsCategoryMomChart');
  if (barCanvas && typeof Chart !== 'undefined') {
    if (categoryMomBarChartInstance) categoryMomBarChartInstance.destroy();
    categoryMomBarChartInstance = new Chart(barCanvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: expCats.map((c) => c.category),
        datasets: [
          {
            label: `Previous Month (${categoriesData.previous_month || 'Prev'})`,
            data: expCats.map((c) => c.previous_month_amount),
            backgroundColor: 'rgba(148, 163, 184, 0.45)',
            borderColor: '#94a3b8',
            borderWidth: 1,
            borderRadius: 5,
          },
          {
            label: `Current Month (${categoriesData.current_month || 'Curr'})`,
            data: expCats.map((c) => c.current_month_amount),
            backgroundColor: 'rgba(59, 130, 246, 0.85)',
            borderColor: '#3b82f6',
            borderWidth: 1,
            borderRadius: 5,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          tooltip: {
            callbacks: { label: (ctx) => `${ctx.dataset.label}: ${formatINR(ctx.raw)}` },
          },
        },
        scales: {
          y: { ticks: { callback: (v) => formatCompactINR(v) } },
        },
      },
    });
  }
}

function renderCategoryBreakdownTable(expCats, curYm, prevYm) {
  const tbody = document.getElementById('categoryBreakdownBody');
  if (!tbody) return;

  if (!expCats.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No expense categories available.</td></tr>`;
    return;
  }

  tbody.innerHTML = expCats
    .map((c) => {
      const sign = c.mom_change_percent >= 0 ? '+' : '';
      const badgeCls =
        c.mom_change_percent > 15
          ? 'badge-danger'
          : c.mom_change_percent < 0
          ? 'badge-success'
          : 'badge-info';
      return `
      <tr>
        <td>
          <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${getCategoryColor(c.category)};margin-right:8px;"></span>
          <strong>${escapeHtml(c.category)}</strong>
        </td>
        <td>${c.transaction_count}</td>
        <td class="amount-cell">${formatINR(c.average_transaction)}</td>
        <td class="amount-cell">${formatINR(c.previous_month_amount)}</td>
        <td class="amount-cell">${formatINR(c.current_month_amount)}</td>
        <td><span class="badge ${badgeCls}">${sign}${c.mom_change_percent}%</span></td>
        <td class="amount-cell amount-expense">
          ${formatINR(c.total_amount)}
          <span style="font-size:0.75rem;color:var(--text-secondary);margin-left:6px;">(${c.percentage_of_expenses}%)</span>
        </td>
      </tr>
    `;
    })
    .join('');
}

function filterRecurringByType(recType, btnEl) {
  if (btnEl && btnEl.parentElement) {
    btnEl.parentElement.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
    btnEl.classList.add('active');
  }
  renderRecurringTable(allRecurringStreams, recType);
}

function renderRecurringTable(items, filterType = 'All') {
  const tbody = document.getElementById('recurringStreamsBody');
  if (!tbody) return;

  const filtered =
    filterType === 'All'
      ? items
      : items.filter((r) => r.recurring_type === filterType);

  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No recurring payments found for filter "${escapeHtml(filterType)}".</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered
    .map((r) => {
      const dueBadge =
        r.days_until_due >= 0 && r.days_until_due <= 7
          ? `<span class="badge badge-warning">In ${r.days_until_due}d</span>`
          : `<span class="badge badge-neutral">${r.days_until_due}d</span>`;
      return `
      <tr>
        <td><strong>${escapeHtml(r.name)}</strong></td>
        <td><span class="badge badge-info">${escapeHtml(r.recurring_type)}</span></td>
        <td>${escapeHtml(r.category)}</td>
        <td>${escapeHtml(r.frequency)} (${r.interval_days}d)</td>
        <td class="amount-cell ${r.type === 'income' ? 'amount-income' : 'amount-expense'}">
          ${r.type === 'income' ? '+' : '-'}${formatINR(r.average_amount)}
        </td>
        <td>${formatDate(r.last_payment_date)}</td>
        <td>${formatDate(r.next_payment_date)} ${dueBadge}</td>
        <td>
          <span class="badge badge-success">${Math.round(r.confidence * 100)}%</span>
          <span style="font-size:0.74rem;color:var(--text-secondary);margin-left:4px;">(${r.occurrences}x)</span>
        </td>
      </tr>
    `;
    })
    .join('');
}

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('monthlyTrendChart')) {
    loadAnalyticsPage();
  }
});
