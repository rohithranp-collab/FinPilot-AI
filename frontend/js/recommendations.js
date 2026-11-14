/**
 * FinPilot AI – AI Financial Recommendations & Personalized Budgets Controller (recommendations.html)
 */

let currentRecommendationsBundle = null;

async function loadRecommendationsPage() {
  try {
    const res = await apiRequest('/api/recommendations');
    currentRecommendationsBundle = res;

    renderRecommendationsKPIs(res);
    renderActionableRecommendations(res.recommendations || []);
    renderCategoryBudgets(res.category_budgets || []);
    renderExcessiveSpending(res.excessive_spending || []);
    renderUpcomingPaymentWarnings(res.upcoming_payment_warnings || []);
  } catch (err) {
    showToast(`Failed to load recommendations: ${err.message}`, 'error');
  }
}

function renderRecommendationsKPIs(res) {
  const scoreEl = document.getElementById('recHealthScore');
  const saveMoEl = document.getElementById('recPotentialMonthly');
  const saveYrEl = document.getElementById('recPotentialAnnual');
  const surplusEl = document.getElementById('recMonthlySurplus');

  if (scoreEl) {
    scoreEl.textContent = `${res.financial_health_score || 0}/100 (${res.health_label || 'N/A'})`;
  }
  const potMo = res.potential_monthly_savings || 0;
  if (saveMoEl) saveMoEl.textContent = formatINR(potMo);
  if (saveYrEl) saveYrEl.textContent = formatINR(potMo * 12);
  if (surplusEl) {
    surplusEl.textContent = `${formatINR(res.monthly_surplus_estimate || 0)} (${res.savings_rate_percent || 0}%)`;
  }
}

function renderActionableRecommendations(recs) {
  const container = document.getElementById('aiRecommendationsCards');
  if (!container) return;

  if (!recs.length) {
    container.innerHTML = `<div class="empty-state"><h4>No Recommendations Available Yet</h4><p>Add transactions to receive personalized AI recommendations.</p></div>`;
    return;
  }

  container.innerHTML = recs
    .map((r) => {
      const badgeCls =
        r.priority === 'High'
          ? 'badge-danger'
          : r.priority === 'Medium'
          ? 'badge-warning'
          : 'badge-info';
      const stepsHtml = (r.action_steps || [])
        .map((s) => `<li style="margin-bottom:4px;">✓ ${escapeHtml(s)}</li>`)
        .join('');
      return `
      <div class="card" style="margin-bottom:0;border-left:4px solid ${getCategoryColor(r.category)};">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:10px;">
          <div>
            <span class="badge ${badgeCls}">${escapeHtml(r.priority)} Priority</span>
            <span class="badge badge-neutral" style="margin-left:6px;">${escapeHtml(r.type)}</span>
            <h3 style="font-size:1.02rem;margin-top:8px;">${escapeHtml(r.title)}</h3>
          </div>
          ${
            r.potential_monthly_savings > 0
              ? `<div class="insight-impact" style="background:var(--success-bg);color:#34d399;">Save ${formatINR(r.potential_monthly_savings)}/mo</div>`
              : ''
          }
        </div>
        <p style="font-size:0.86rem;color:var(--text-secondary);margin-bottom:12px;">
          ${escapeHtml(r.explanation)}
        </p>
        <div style="background:rgba(10,18,38,0.65);padding:10px 14px;border-radius:var(--radius-sm);font-size:0.8rem;color:#cbd5e1;">
          <strong style="display:block;margin-bottom:4px;color:#93c5fd;">Recommended Action Plan:</strong>
          <ul style="list-style:none;padding:0;">${stepsHtml}</ul>
        </div>
      </div>
    `;
    })
    .join('');
}

function renderCategoryBudgets(budgets) {
  const container = document.getElementById('categoryBudgetsContainer');
  if (!container) return;

  if (!budgets.length) {
    container.innerHTML = `<div class="empty-state"><p>No category budgets generated yet.</p></div>`;
    return;
  }

  container.innerHTML = budgets
    .map((b) => {
      const pct = Math.min(100, Math.max(0, b.utilization_percent || 0));
      const barCls =
        b.status === 'Exceeded'
          ? 'danger'
          : b.status === 'Warning'
          ? 'warning'
          : 'success';
      const statusBadge =
        b.status === 'Exceeded'
          ? 'badge-danger'
          : b.status === 'Warning'
          ? 'badge-warning'
          : 'badge-success';

      return `
      <div class="insight-item" style="flex-direction:column;align-items:stretch;border-left-color:${getCategoryColor(b.category)};">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
          <div>
            <strong style="font-size:0.96rem;">${escapeHtml(b.category)}</strong>
            <span class="badge ${statusBadge}" style="margin-left:8px;">${escapeHtml(b.status)} (${b.utilization_percent}%)</span>
            ${b.is_custom ? '<span class="badge badge-user" style="margin-left:4px;">Custom Limit</span>' : '<span class="badge badge-info" style="margin-left:4px;">AI Limit</span>'}
          </div>
          <div style="display:flex;align-items:center;gap:12px;">
            <span class="amount-cell">
              <strong>${formatINR(b.current_spent)}</strong>
              <span style="color:var(--text-secondary);"> / ${formatINR(b.monthly_limit)}</span>
            </span>
            <button class="btn btn-secondary btn-xs" onclick="openBudgetEditModal('${escapeHtml(b.category)}', ${b.monthly_limit}, ${b.recommended_limit})">
              Customize Limit
            </button>
          </div>
        </div>
        <div class="progress-track">
          <div class="progress-fill ${barCls}" style="width:${pct}%;"></div>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:0.78rem;color:var(--text-secondary);flex-wrap:wrap;gap:8px;">
          <span>${escapeHtml(b.explanation)}</span>
          <span>${b.remaining_budget >= 0 ? `Remaining: ${formatINR(b.remaining_budget)}` : `Over by: ${formatINR(Math.abs(b.remaining_budget))}`}</span>
        </div>
      </div>
    `;
    })
    .join('');
}

function renderExcessiveSpending(items) {
  const container = document.getElementById('excessiveSpendingContainer');
  if (!container) return;

  if (!items.length) {
    container.innerHTML = `<div class="empty-state"><p>All categories are currently within healthy historical and budget thresholds.</p></div>`;
    return;
  }

  container.innerHTML = items
    .map(
      (item) => `
    <div class="insight-item ${item.severity === 'High' ? 'danger' : 'warning'}">
      <div class="insight-body">
        <h4>${escapeHtml(item.category)} <span class="badge badge-danger" style="margin-left:6px;">+${item.mom_increase_percent}% MoM</span></h4>
        <p>${escapeHtml(item.explanation)}</p>
      </div>
      <div class="insight-impact" style="background:var(--danger-bg);color:#fb7185;">
        ${formatINR(item.current_spent)}
      </div>
    </div>
  `
    )
    .join('');
}

function renderUpcomingPaymentWarnings(warnings) {
  const container = document.getElementById('upcomingWarningsContainer');
  if (!container) return;

  if (!warnings.length) {
    container.innerHTML = `<div class="empty-state"><p>No urgent recurring bills due in the next 14 days.</p></div>`;
    return;
  }

  container.innerHTML = warnings
    .map(
      (w) => `
    <div class="insight-item ${w.urgency === 'High' ? 'warning' : 'info'}">
      <div class="insight-body">
        <h4>${escapeHtml(w.name)} <span class="badge badge-warning" style="margin-left:6px;">${escapeHtml(w.recurring_type)}</span></h4>
        <p>${escapeHtml(w.warning_message)}</p>
      </div>
      <div class="insight-impact">${formatINR(w.amount)}</div>
    </div>
  `
    )
    .join('');
}

function openBudgetEditModal(category, currentLimit, recommendedLimit) {
  document.getElementById('budgetModalCategory').value = category;
  document.getElementById('budgetModalCategoryDisplay').textContent = category;
  document.getElementById('budgetModalLimit').value = currentLimit;
  document.getElementById('budgetModalAiHint').textContent = `AI Recommended Monthly Limit for ${category}: ${formatINR(recommendedLimit)}`;
  openModal('editBudgetModal');
}

async function submitBudgetUpdate(event) {
  event.preventDefault();
  const category = document.getElementById('budgetModalCategory').value;
  const monthlyLimit = parseFloat(document.getElementById('budgetModalLimit').value);

  try {
    const res = await apiRequest('/api/recommendations/budgets', {
      method: 'PUT',
      body: JSON.stringify({ category, monthly_limit: monthlyLimit }),
    });
    closeModal('editBudgetModal');
    showToast(res.message || 'Budget updated!', 'success');
    await loadRecommendationsPage();
  } catch (err) {
    showToast(`Failed to update budget: ${err.message}`, 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('aiRecommendationsCards')) {
    loadRecommendationsPage();
  }
});
