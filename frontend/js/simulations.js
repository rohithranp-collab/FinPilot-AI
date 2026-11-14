/**
 * FinPilot AI – What-If Financial Simulations Controller (simulations.html)
 */

let simulationTrajectoryChartInstance = null;
let savedSimulationsList = [];

const SCENARIO_LABELS = {
  large_purchase: 'Large One-Time Purchase',
  monthly_emi: 'Monthly EMI / New Loan',
  loan_repayment: 'Loan Prepayment / Payoff',
  savings_target: 'Savings Goal Target',
  additional_expense: 'Additional Recurring Expense',
};

async function loadSimulationsPage() {
  try {
    const res = await apiRequest('/api/simulations');
    savedSimulationsList = res.simulations || [];
    renderSavedSimulationsHistory(savedSimulationsList);

    if (savedSimulationsList.length > 0) {
      renderSimulationResult(savedSimulationsList[0]);
    }
  } catch (err) {
    showToast(`Failed to load simulations: ${err.message}`, 'error');
  }
}

function applySimulationPreset(presetType) {
  const nameEl = document.getElementById('simName');
  const typeEl = document.getElementById('simScenarioType');
  const amtEl = document.getElementById('simTotalAmount');
  const durEl = document.getElementById('simDurationMonths');
  const rateEl = document.getElementById('simInterestRate');
  const downEl = document.getElementById('simDownPayment');
  const extraEl = document.getElementById('simExtraMonthly');

  if (presetType === 'large_purchase') {
    nameEl.value = 'Europe Family Vacation / Home Renovation';
    typeEl.value = 'large_purchase';
    amtEl.value = '120000';
    durEl.value = '12';
    rateEl.value = '0';
    downEl.value = '0';
    extraEl.value = '0';
  } else if (presetType === 'monthly_emi') {
    nameEl.value = 'New Electric SUV / Gadget Loan EMI';
    typeEl.value = 'monthly_emi';
    amtEl.value = '240000';
    durEl.value = '18';
    rateEl.value = '10.5';
    downEl.value = '40000';
    extraEl.value = '0';
  } else if (presetType === 'loan_repayment') {
    nameEl.value = 'Car Loan Accelerated Prepayment';
    typeEl.value = 'loan_repayment';
    amtEl.value = '180000';
    durEl.value = '18';
    rateEl.value = '9.5';
    downEl.value = '35000';
    extraEl.value = '4000';
  } else if (presetType === 'savings_target') {
    nameEl.value = 'Emergency & Investment Corpus ₹3,50,000';
    typeEl.value = 'savings_target';
    amtEl.value = '350000';
    durEl.value = '12';
    rateEl.value = '7.0';
    downEl.value = '50000';
    extraEl.value = '0';
  } else if (presetType === 'additional_expense') {
    nameEl.value = 'Upgraded 3BHK Apartment Rent Difference';
    typeEl.value = 'additional_expense';
    amtEl.value = '12000';
    durEl.value = '12';
    rateEl.value = '0';
    downEl.value = '25000';
    extraEl.value = '0';
  }

  updateScenarioFieldLabels();
  showToast(`Loaded "${nameEl.value}" preset. Click "Run Financial Simulation" to evaluate!`, 'info');
}

function updateScenarioFieldLabels() {
  const type = document.getElementById('simScenarioType')?.value || 'large_purchase';
  const amtLabel = document.getElementById('simAmountLabel');
  const downLabel = document.getElementById('simDownLabel');
  const rateGroup = document.getElementById('simRateGroup');
  const extraGroup = document.getElementById('simExtraGroup');

  if (type === 'large_purchase') {
    if (amtLabel) amtLabel.textContent = 'Purchase Cost (₹)';
    if (downLabel) downLabel.textContent = 'Additional Upfront Fee (₹)';
    if (rateGroup) rateGroup.style.opacity = '0.5';
    if (extraGroup) extraGroup.style.display = 'none';
  } else if (type === 'monthly_emi') {
    if (amtLabel) amtLabel.textContent = 'Total Asset / Loan Price (₹)';
    if (downLabel) downLabel.textContent = 'Upfront Down Payment (₹)';
    if (rateGroup) rateGroup.style.opacity = '1';
    if (extraGroup) extraGroup.style.display = 'none';
  } else if (type === 'loan_repayment') {
    if (amtLabel) amtLabel.textContent = 'Outstanding Loan Principal (₹)';
    if (downLabel) downLabel.textContent = 'Lump-Sum Prepayment Now (₹)';
    if (rateGroup) rateGroup.style.opacity = '1';
    if (extraGroup) extraGroup.style.display = 'flex';
  } else if (type === 'savings_target') {
    if (amtLabel) amtLabel.textContent = 'Target Savings Goal (₹)';
    if (downLabel) downLabel.textContent = 'Initial Seed Deposit (₹)';
    if (rateGroup) rateGroup.style.opacity = '1';
    if (extraGroup) extraGroup.style.display = 'none';
  } else {
    if (amtLabel) amtLabel.textContent = 'New Monthly Expense Amount (₹/mo)';
    if (downLabel) downLabel.textContent = 'One-Time Setup / Deposit (₹)';
    if (rateGroup) rateGroup.style.opacity = '0.5';
    if (extraGroup) extraGroup.style.display = 'none';
  }
}

async function submitSimulationForm(event) {
  event.preventDefault();
  const payload = {
    name: document.getElementById('simName').value.trim(),
    scenario_type: document.getElementById('simScenarioType').value,
    total_amount: parseFloat(document.getElementById('simTotalAmount').value),
    duration_months: parseInt(document.getElementById('simDurationMonths').value, 10) || 12,
    interest_rate: parseFloat(document.getElementById('simInterestRate').value || '0') || 0.0,
    down_payment: parseFloat(document.getElementById('simDownPayment').value || '0') || 0.0,
    extra_monthly_payment: parseFloat(document.getElementById('simExtraMonthly')?.value || '0') || 0.0,
    start_month_offset: 0,
  };

  try {
    const result = await apiRequest('/api/simulations', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    showToast(`Simulation "${result.name}" evaluated! Risk Level: ${result.risk_level}`, 'success');
    renderSimulationResult(result);
    const listRes = await apiRequest('/api/simulations');
    savedSimulationsList = listRes.simulations || [];
    renderSavedSimulationsHistory(savedSimulationsList);
  } catch (err) {
    showToast(`Simulation Error: ${err.message}`, 'error');
  }
}

function renderSimulationResult(sim) {
  if (!sim) return;
  const details = sim.details || {};

  const titleEl = document.getElementById('simResultTitle');
  const riskBadge = document.getElementById('simResultRiskBadge');
  const summaryLine = document.getElementById('simResultSummaryLine');
  const verdictBox = document.getElementById('simResultVerdict');

  if (titleEl) titleEl.textContent = `${sim.name} (${SCENARIO_LABELS[sim.scenario_type] || sim.scenario_type})`;
  if (riskBadge) {
    const cls =
      sim.risk_level === 'Low'
        ? 'badge-success'
        : sim.risk_level === 'Moderate'
        ? 'badge-warning'
        : 'badge-danger';
    riskBadge.className = `badge ${cls}`;
    riskBadge.textContent = `${sim.risk_level} Risk`;
  }
  if (summaryLine) {
    summaryLine.textContent = details.scenario_summary || '';
  }
  if (verdictBox) {
    const vCls =
      sim.risk_level === 'Low'
        ? 'positive'
        : sim.risk_level === 'Moderate'
        ? 'warning'
        : 'danger';
    verdictBox.className = `insight-item ${vCls}`;
    verdictBox.innerHTML = `
      <div class="insight-body">
        <h4>AI Financial Impact Verdict</h4>
        <p>${escapeHtml(sim.verdict)}</p>
      </div>
    `;
  }

  // Update KPI Cards
  const beforeEl = document.getElementById('simBalBefore');
  const afterEl = document.getElementById('simBalAfter');
  const monthlyImpactEl = document.getElementById('simMonthlyImpactVal');
  const minBalEl = document.getElementById('simMinBalReached');

  if (beforeEl) beforeEl.textContent = formatINR(sim.projected_balance_before);
  if (afterEl) afterEl.textContent = formatINR(sim.projected_balance_after);
  if (monthlyImpactEl) {
    monthlyImpactEl.textContent = `${formatINR(sim.monthly_impact)}/mo`;
  }
  if (minBalEl) {
    minBalEl.textContent = formatINR(details.minimum_balance_reached ?? sim.projected_balance_after);
  }

  const subBefore = document.getElementById('simSubBefore');
  const subAfter = document.getElementById('simSubAfter');
  const subImpact = document.getElementById('simSubImpact');
  const subMin = document.getElementById('simSubMin');

  if (subBefore) {
    subBefore.textContent = `Starting Balance: ${formatINR(sim.current_balance_baseline)}`;
  }
  if (subAfter) {
    const diff = (sim.projected_balance_after || 0) - (sim.projected_balance_before || 0);
    subAfter.textContent = `Difference vs Baseline: ${diff >= 0 ? '+' : ''}${formatINR(diff)}`;
  }
  if (subImpact) {
    subImpact.textContent = `One-Time Upfront: ${formatINR(sim.one_time_impact)}`;
  }
  if (subMin) {
    if (sim.scenario_type === 'loan_repayment' && details.interest_saved > 0) {
      subMin.textContent = `Interest Saved: ${formatINR(details.interest_saved)} (${details.months_saved} mos saved)`;
    } else if (sim.scenario_type === 'savings_target' && details.accumulated_savings_goal > 0) {
      subMin.textContent = `Accumulated Corpus: ${formatINR(details.accumulated_savings_goal)}`;
    } else {
      subMin.textContent = `Surplus After: ${formatINR(details.post_decision_monthly_surplus || 0)}/mo`;
    }
  }

  // Render Trajectory Chart
  const timeline = details.timeline || [];
  renderSimulationChart(timeline, sim.name);
  renderSimulationScheduleTable(timeline);
}

function renderSimulationChart(timeline, simName) {
  const canvas = document.getElementById('simulationTrajectoryChart');
  if (!canvas || typeof Chart === 'undefined') return;

  if (simulationTrajectoryChartInstance) {
    simulationTrajectoryChartInstance.destroy();
  }

  if (!timeline.length) return;

  const datasets = [
    {
      label: 'Baseline Balance (Without Decision)',
      data: timeline.map((t) => t.baseline_balance),
      borderColor: '#94a3b8',
      backgroundColor: 'rgba(148, 163, 184, 0.08)',
      borderWidth: 2,
      borderDash: [5, 5],
      pointRadius: 3,
      tension: 0.3,
    },
    {
      label: `Simulated Balance (${simName})`,
      data: timeline.map((t) => t.simulated_balance),
      borderColor: '#3b82f6',
      backgroundColor: 'rgba(59, 130, 246, 0.16)',
      borderWidth: 3,
      fill: true,
      pointRadius: 3,
      tension: 0.3,
    },
  ];

  if (timeline[0] && timeline[0].goal_corpus !== null && timeline[0].goal_corpus !== undefined) {
    datasets.push({
      label: 'Accumulated Target Corpus',
      data: timeline.map((t) => t.goal_corpus),
      borderColor: '#10b981',
      backgroundColor: 'rgba(16, 185, 129, 0.12)',
      borderWidth: 2.5,
      pointRadius: 3,
      tension: 0.3,
    });
  }

  simulationTrajectoryChartInstance = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      labels: timeline.map((t) => t.label),
      datasets,
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
        y: { ticks: { callback: (v) => formatCompactINR(v) } },
      },
    },
  });
}

function renderSimulationScheduleTable(timeline) {
  const tbody = document.getElementById('simulationScheduleBody');
  if (!tbody) return;

  if (!timeline.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Run a simulation to view the month-by-month projection schedule.</td></tr>`;
    return;
  }

  tbody.innerHTML = timeline
    .map(
      (row) => `
    <tr>
      <td><strong>${escapeHtml(row.label)}</strong></td>
      <td class="amount-cell">${formatINR(row.baseline_balance)}</td>
      <td class="amount-cell amount-expense">-${formatINR(row.monthly_decision_outflow)}</td>
      <td class="amount-cell ${row.net_monthly_cashflow_after >= 0 ? 'amount-income' : 'amount-expense'}">
        ${row.net_monthly_cashflow_after >= 0 ? '+' : ''}${formatINR(row.net_monthly_cashflow_after)}
      </td>
      <td class="amount-cell" style="color:${row.simulated_balance >= 0 ? '#38bdf8' : '#fb7185'};">
        <strong>${formatINR(row.simulated_balance)}</strong>
      </td>
    </tr>
  `
    )
    .join('');
}

function renderSavedSimulationsHistory(items) {
  const tbody = document.getElementById('savedSimulationsBody');
  if (!tbody) return;

  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No saved simulations yet.</td></tr>`;
    return;
  }

  tbody.innerHTML = items
    .map((s) => {
      const riskCls =
        s.risk_level === 'Low'
          ? 'badge-success'
          : s.risk_level === 'Moderate'
          ? 'badge-warning'
          : 'badge-danger';
      return `
      <tr>
        <td>
          <strong>${escapeHtml(s.name)}</strong>
          ${s.is_demo ? '<span class="badge badge-demo" style="margin-left:6px;">Demo</span>' : '<span class="badge badge-user" style="margin-left:6px;">User</span>'}
        </td>
        <td>${escapeHtml(SCENARIO_LABELS[s.scenario_type] || s.scenario_type)}</td>
        <td class="amount-cell">${formatINR(s.total_amount)} (${s.duration_months}m)</td>
        <td class="amount-cell">${formatINR(s.projected_balance_before)}</td>
        <td class="amount-cell">${formatINR(s.projected_balance_after)}</td>
        <td><span class="badge ${riskCls}">${escapeHtml(s.risk_level)}</span></td>
        <td>
          <div style="display:flex;gap:6px;">
            <button class="btn btn-secondary btn-xs" onclick="selectSavedSimulation(${s.id})">View</button>
            <button class="btn btn-danger btn-xs" onclick="deleteSavedSimulation(${s.id})">Delete</button>
          </div>
        </td>
      </tr>
    `;
    })
    .join('');
}

function selectSavedSimulation(simId) {
  const found = savedSimulationsList.find((s) => s.id === simId);
  if (found) {
    renderSimulationResult(found);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

async function deleteSavedSimulation(simId) {
  try {
    await apiRequest(`/api/simulations/${simId}`, { method: 'DELETE' });
    showToast(`Simulation #${simId} deleted.`, 'info');
    await loadSimulationsPage();
  } catch (err) {
    showToast(`Failed to delete simulation: ${err.message}`, 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('simulationTrajectoryChart')) {
    updateScenarioFieldLabels();
    loadSimulationsPage();
  }
});
