/**
 * FinPilot AI – Cash Flow Forecasting, Prediction Accuracy & Anomaly Detection Controller (predictions.html)
 */

let mainForecastChartInstance = null;
let accuracyBacktestChartInstance = null;
let fullForecastResponse = null;
let selectedHorizon = 90;
let allDetectedAnomalies = [];

async function loadPredictionsPage() {
  try {
    const [forecast, accuracy, anomalies] = await Promise.all([
      apiRequest('/api/predictions/cashflow?horizon=90'),
      apiRequest('/api/predictions/accuracy'),
      apiRequest('/api/anomalies'),
    ]);

    fullForecastResponse = forecast;
    allDetectedAnomalies = anomalies.anomalies || [];

    renderForecastSufficiencyBanner(forecast);
    renderHorizonCards(forecast);
    renderMainForecastChart(forecast, selectedHorizon);
    renderMethodologyDetails(forecast);
    renderPredictionAccuracySection(accuracy);
    renderAnomaliesSection(anomalies, 'All');
  } catch (err) {
    showToast(`Failed to load predictions: ${err.message}`, 'error');
  }
}

function renderForecastSufficiencyBanner(forecast) {
  const bannerEl = document.getElementById('dataSufficiencyBanner');
  if (!bannerEl) return;

  if (!forecast.sufficient_data) {
    bannerEl.innerHTML = `
      <div class="insight-item warning" style="margin-bottom:20px;">
        <div class="insight-body">
          <h4>⚠️ Insufficient Historical Data Warning</h4>
          <p>${escapeHtml(forecast.data_status_message)}</p>
        </div>
        <span class="badge badge-warning">Confidence: ${escapeHtml(forecast.confidence_level)}</span>
      </div>
    `;
  } else {
    bannerEl.innerHTML = `
      <div class="insight-item positive" style="margin-bottom:20px;">
        <div class="insight-body">
          <h4>✅ Verified Historical Dataset (${forecast.transaction_count || 0} Transactions across ${forecast.span_days || 0} Days)</h4>
          <p>${escapeHtml(forecast.data_status_message)}</p>
        </div>
        <span class="badge badge-success">Confidence: ${escapeHtml(forecast.confidence_level)} (${Math.round((forecast.confidence_score || 0) * 100)}%)</span>
      </div>
    `;
  }
}

function renderHorizonCards(forecast) {
  const horizons = forecast.horizons || {};
  [7, 30, 90].forEach((h) => {
    const data = horizons[`${h}_days`] || {};
    const balEl = document.getElementById(`predBalance${h}d`);
    const subEl = document.getElementById(`predSub${h}d`);
    const bandEl = document.getElementById(`predBand${h}d`);
    const confEl = document.getElementById(`predConf${h}d`);

    if (balEl) balEl.textContent = formatINR(data.predicted_balance);
    if (confEl) confEl.textContent = `${data.confidence_percent || 0}% Conf.`;
    if (subEl) {
      subEl.innerHTML = `
        <span class="amount-income">+${formatINR(data.predicted_income)}</span> /
        <span class="amount-expense">-${formatINR(data.predicted_expense)}</span>
      `;
    }
    if (bandEl) {
      bandEl.textContent = `90% Band: ${formatINR(data.lower_bound_balance)} to ${formatINR(data.upper_bound_balance)} (±${formatINR(data.uncertainty_margin)})`;
    }
  });
}

function switchPredictionHorizon(days, btnEl) {
  selectedHorizon = days;
  if (btnEl && btnEl.parentElement) {
    btnEl.parentElement.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
    btnEl.classList.add('active');
  }
  if (fullForecastResponse) {
    renderMainForecastChart(fullForecastResponse, days);
  }
}

function renderMainForecastChart(forecast, horizonDays = 90) {
  const canvas = document.getElementById('mainForecastChart');
  if (!canvas || typeof Chart === 'undefined') return;

  const hist = (forecast.historical_daily_series || []).slice(-20);
  const fut = (forecast.daily_series || []).slice(0, horizonDays);

  const labels = [
    ...hist.map((d) => formatDate(d.date)),
    ...fut.map((d) => formatDate(d.date)),
  ];

  const histLen = hist.length;
  const lastActual = histLen > 0 ? hist[histLen - 1].actual_balance : forecast.current_balance;

  const actualSeries = [
    ...hist.map((d) => d.actual_balance),
    ...Array(fut.length).fill(null),
  ];
  const predSeries = [
    ...Array(Math.max(0, histLen - 1)).fill(null),
    ...(histLen > 0 ? [lastActual] : []),
    ...fut.map((d) => d.predicted_balance),
  ];
  const upperSeries = [
    ...Array(Math.max(0, histLen - 1)).fill(null),
    ...(histLen > 0 ? [lastActual] : []),
    ...fut.map((d) => d.upper_bound_balance),
  ];
  const lowerSeries = [
    ...Array(Math.max(0, histLen - 1)).fill(null),
    ...(histLen > 0 ? [lastActual] : []),
    ...fut.map((d) => d.lower_bound_balance),
  ];

  if (mainForecastChartInstance) {
    mainForecastChartInstance.destroy();
  }

  mainForecastChartInstance = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Actual Historical Balance',
          data: actualSeries,
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56, 189, 248, 0.14)',
          borderWidth: 2.5,
          pointRadius: 2,
          tension: 0.3,
        },
        {
          label: `Forecasted Balance (${horizonDays} Days)`,
          data: predSeries,
          borderColor: '#10b981',
          backgroundColor: 'rgba(16, 185, 129, 0.12)',
          borderWidth: 2.5,
          borderDash: [6, 4],
          pointRadius: 2,
          tension: 0.3,
        },
        {
          label: 'Upper Uncertainty Bound',
          data: upperSeries,
          borderColor: 'rgba(99, 102, 241, 0.3)',
          backgroundColor: 'rgba(99, 102, 241, 0.12)',
          borderWidth: 1,
          pointRadius: 0,
          fill: '+1',
          tension: 0.3,
        },
        {
          label: 'Lower Uncertainty Bound',
          data: lowerSeries,
          borderColor: 'rgba(244, 63, 94, 0.3)',
          backgroundColor: 'transparent',
          borderWidth: 1,
          pointRadius: 0,
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
            label: (ctx) => {
              if (ctx.raw === null || ctx.raw === undefined) return null;
              return `${ctx.dataset.label}: ${formatINR(ctx.raw)}`;
            },
          },
        },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 12 } },
        y: { ticks: { callback: (v) => formatCompactINR(v) } },
      },
    },
  });
}

function renderMethodologyDetails(forecast) {
  const m = forecast.methodology || {};
  const titleEl = document.getElementById('methodologyName');
  const descEl = document.getElementById('methodologyDesc');
  const listEl = document.getElementById('methodologyComponents');
  const warnEl = document.getElementById('forecastWarningsList');

  if (titleEl) titleEl.textContent = m.name || 'Hybrid Time-Series Model';
  if (descEl) descEl.textContent = m.description || '';
  if (listEl) {
    listEl.innerHTML = (m.components || [])
      .map(
        (c) => `<li style="margin-bottom:8px;color:var(--text-secondary);font-size:0.85rem;">• ${escapeHtml(c)}</li>`
      )
      .join('');
  }
  if (warnEl) {
    const warnings = forecast.risk_warnings || [];
    if (!warnings.length) {
      warnEl.innerHTML = `<div class="insight-item positive"><div class="insight-body"><h4>No Liquidity Shortfalls Projected</h4><p>Your account balance remains positive across all 7-day, 30-day, and 90-day baseline and stress horizons.</p></div></div>`;
    } else {
      warnEl.innerHTML = warnings
        .map(
          (w) => `<div class="insight-item warning"><div class="insight-body"><h4>Cash Flow Risk Alert</h4><p>${escapeHtml(w)}</p></div></div>`
        )
        .join('');
    }
  }
}

function renderPredictionAccuracySection(accuracy) {
  const statusEl = document.getElementById('accuracyStatusMessage');
  const metricsGrid = document.getElementById('accuracyMetricsGrid');
  const tbody = document.getElementById('accuracyTableBody');

  if (statusEl) {
    statusEl.textContent = accuracy.message || '';
  }

  if (!accuracy.sufficient_data || !accuracy.metrics) {
    if (metricsGrid) {
      metricsGrid.innerHTML = `
        <div class="card" style="grid-column:1 / -1;">
          <div class="empty-state">
            <h4>Insufficient Historical Span for Validated Accuracy Metrics</h4>
            <p>${escapeHtml(accuracy.message || 'At least 30 days of transaction history are required to evaluate out-of-sample MAE and MAPE.')}</p>
          </div>
        </div>
      `;
    }
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty-state">Accuracy checkpoints withheld until 30+ days of history are available.</td></tr>`;
    }
    return;
  }

  const m = accuracy.metrics;
  const accPctEl = document.getElementById('accMetricPercent');
  const maeEl = document.getElementById('accMetricMae');
  const mapeEl = document.getElementById('accMetricMape');
  const covEl = document.getElementById('accMetricCoverage');

  if (accPctEl) accPctEl.textContent = `${m.accuracy_percent}% (${m.rating})`;
  if (maeEl) maeEl.textContent = formatINR(m.mae_balance);
  if (mapeEl) mapeEl.textContent = `${m.mape_percent}%`;
  if (covEl) covEl.textContent = `${m.confidence_band_coverage_percent}%`;

  const records = accuracy.comparison_records || [];
  if (tbody) {
    tbody.innerHTML = records
      .map(
        (r) => `
      <tr>
        <td>${formatDate(r.origin_date)}</td>
        <td>${formatDate(r.target_date)} (${r.horizon_days}d)</td>
        <td class="amount-cell">${formatINR(r.predicted_balance)}</td>
        <td class="amount-cell">${formatINR(r.actual_balance)}</td>
        <td class="amount-cell">${formatINR(r.absolute_error_balance)}</td>
        <td><span class="badge ${r.percentage_error_balance < 15 ? 'badge-success' : 'badge-warning'}">${r.percentage_error_balance}%</span></td>
        <td><span class="badge badge-info">${escapeHtml(r.source)}</span></td>
      </tr>
    `
      )
      .join('');
  }

  // Render Predicted vs Actual Backtest Chart
  const canvas = document.getElementById('accuracyBacktestChart');
  if (canvas && typeof Chart !== 'undefined' && records.length > 0) {
    if (accuracyBacktestChartInstance) accuracyBacktestChartInstance.destroy();
    accuracyBacktestChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: records.map((r) => formatDate(r.target_date)),
        datasets: [
          {
            label: 'Predicted Balance',
            data: records.map((r) => r.predicted_balance),
            backgroundColor: 'rgba(59, 130, 246, 0.8)',
            borderColor: '#3b82f6',
            borderWidth: 1,
            borderRadius: 5,
          },
          {
            label: 'Actual Realized Balance',
            data: records.map((r) => r.actual_balance),
            backgroundColor: 'rgba(16, 185, 129, 0.8)',
            borderColor: '#10b981',
            borderWidth: 1,
            borderRadius: 5,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
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

function filterAnomaliesList(filterType, btnEl) {
  if (btnEl && btnEl.parentElement) {
    btnEl.parentElement.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
    btnEl.classList.add('active');
  }
  renderAnomaliesSection({ anomalies: allDetectedAnomalies }, filterType);
}

function renderAnomaliesSection(anomaliesData, filterType = 'All') {
  const listEl = document.getElementById('predictionsAnomaliesList');
  if (!listEl) return;

  const raw = anomaliesData.anomalies || [];
  const filtered =
    filterType === 'All'
      ? raw
      : raw.filter((a) => a.anomaly_type === filterType);

  if (!filtered.length) {
    listEl.innerHTML = `<div class="empty-state"><p>No anomalies found for filter "${escapeHtml(filterType)}".</p></div>`;
    return;
  }

  listEl.innerHTML = filtered
    .map(
      (a) => `
    <div class="insight-item ${a.severity === 'High' ? 'danger' : 'warning'}">
      <div class="insight-body">
        <h4>
          ${escapeHtml(a.description)}
          <span class="badge ${a.severity === 'High' ? 'badge-danger' : 'badge-warning'}" style="margin-left:8px;">
            ${escapeHtml(a.severity)} Severity • ${escapeHtml(a.anomaly_type)}
          </span>
        </h4>
        <p>${escapeHtml(a.explanation)}</p>
        <div style="font-size:0.76rem;color:var(--text-muted);margin-top:6px;">
          Date: <strong>${formatDate(a.date)}</strong> • Category: <strong>${escapeHtml(a.category)}</strong> •
          Category Baseline Mean: <strong>${formatINR(a.historical_category_average)}</strong> •
          Multiplier: <strong>${a.deviation_multiple}x</strong> • Detector: ${escapeHtml(a.detection_method)}
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

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('mainForecastChart')) {
    loadPredictionsPage();
  }
});
