/**
 * FinPilot AI – Core Application Utilities, API Client & Shared UI Shell
 */

const FINPILOT_CONFIG = {
  /**
   * Use relative API URLs ('') by default so frontend and backend work seamlessly
   * on the same domain in production (Render) and when served directly by FastAPI.
   * Only falls back to local port 8000 when opened via file:// or a separate local static port.
   */
  getApiBase() {
    const { protocol, hostname, port } = window.location;
    if (protocol === 'file:') {
      return 'http://127.0.0.1:8000';
    }
    const isLocalHost = hostname === 'localhost' || hostname === '127.0.0.1';
    const isSeparateStaticDevPort = ['3000', '5500', '5501', '8080'].includes(port);
    if (isLocalHost && isSeparateStaticDevPort) {
      return `http://${hostname}:8000`;
    }
    return '';
  }
};

const API_BASE = FINPILOT_CONFIG.getApiBase();

/**
 * Format number as Indian Rupee (₹) with Indian numbering system (lakhs/crores)
 */
function formatINR(value, showDecimals = false) {
  const num = Number(value || 0);
  const isNegative = num < 0;
  const absVal = Math.abs(num);
  const formatted = absVal.toLocaleString('en-IN', {
    minimumFractionDigits: showDecimals ? 2 : 0,
    maximumFractionDigits: showDecimals ? 2 : 0,
  });
  return `${isNegative ? '-₹' : '₹'}${formatted}`;
}

/**
 * Format compact INR for chart axes (e.g. ₹1.2L, ₹45k)
 */
function formatCompactINR(value) {
  const num = Number(value || 0);
  const sign = num < 0 ? '-' : '';
  const abs = Math.abs(num);
  if (abs >= 10000000) return `${sign}₹${(abs / 10000000).toFixed(2)}Cr`;
  if (abs >= 100000) return `${sign}₹${(abs / 100000).toFixed(1)}L`;
  if (abs >= 1000) return `${sign}₹${(abs / 1000).toFixed(0)}k`;
  return `${sign}₹${abs.toFixed(0)}`;
}

/**
 * Format ISO date YYYY-MM-DD into readable DD Mon YYYY
 */
function formatDate(dateStr) {
  if (!dateStr) return '—';
  const parts = String(dateStr).slice(0, 10).split('-');
  if (parts.length !== 3) return dateStr;
  const d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

/**
 * Unified Fetch Wrapper with Relative API URL Support & Error Handling
 */
async function apiRequest(endpoint, options = {}) {
  const normalizedEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  const url = `${API_BASE}${normalizedEndpoint}`;
  const defaultHeaders = {};
  if (!(options.body instanceof FormData)) {
    defaultHeaders['Content-Type'] = 'application/json';
  }
  const config = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...(options.headers || {}),
    },
  };

  const response = await fetch(url, config);
  let data = null;
  try {
    data = await response.json();
  } catch (_) {
    data = null;
  }

  if (!response.ok) {
    const errMsg =
      (data && (data.detail || data.message)) ||
      `Request failed with status ${response.status}`;
    throw new Error(errMsg);
  }
  return data;
}

/**
 * Display Toast Notification
 */
function showToast(message, type = 'info') {
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
    <span>${escapeHtml(message)}</span>
    <button onclick="this.parentElement.parentElement.remove()" style="background:none;border:none;color:#94a3b8;cursor:pointer;font-size:1rem;">&times;</button>
  </div>`;
  container.appendChild(toast);

  setTimeout(() => {
    if (toast.parentElement) {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(8px)';
      setTimeout(() => toast.remove(), 220);
    }
  }, 4200);
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Configure Chart.js Global Dark Theme
 */
function configureChartDefaults() {
  if (typeof Chart === 'undefined') return;
  Chart.defaults.color = '#94a3b8';
  Chart.defaults.font.family = "'Inter', sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  Chart.defaults.scale.grid.color = 'rgba(148, 163, 184, 0.08)';
}

/**
 * Category Color Palette
 */
const CATEGORY_COLORS = {
  'Food': '#3b82f6',
  'Shopping': '#8b5cf6',
  'Rent': '#06b6d4',
  'EMI and Loans': '#f43f5e',
  'Transportation': '#10b981',
  'Utilities': '#f59e0b',
  'Healthcare': '#ec4899',
  'Entertainment': '#6366f1',
  'Education': '#14b8a6',
  'Salary': '#22c55e',
  'Freelance Income': '#38bdf8',
  'Other': '#64748b',
};

function getCategoryColor(cat) {
  return CATEGORY_COLORS[cat] || '#3b82f6';
}

/**
 * Seed / Reset Demo Data Handler
 */
async function handleSeedDemoData(reloadCallback) {
  try {
    showToast('Seeding realistic Indian Rupee (₹) demo data...', 'info');
    const res = await apiRequest('/api/transactions/seed-demo', { method: 'POST' });
    showToast(
      `Seeded ${res.seeded_transactions} demo transactions & ${res.detected_recurring_streams} recurring streams!`,
      'success'
    );
    await refreshSidebarStatus();
    if (typeof reloadCallback === 'function') {
      await reloadCallback();
    } else {
      window.location.reload();
    }
  } catch (err) {
    showToast(`Failed to seed demo data: ${err.message}`, 'error');
  }
}

/**
 * Clear Demo Data Handler (preserves user-entered transactions)
 */
async function handleClearDemoData(reloadCallback) {
  try {
    const res = await apiRequest('/api/transactions/demo', { method: 'DELETE' });
    showToast(
      `Cleared ${res.deleted_demo_transactions} demo transactions. (${res.remaining_user_transactions} user transactions kept).`,
      'info'
    );
    await refreshSidebarStatus();
    if (typeof reloadCallback === 'function') {
      await reloadCallback();
    } else {
      window.location.reload();
    }
  } catch (err) {
    showToast(`Failed to clear demo data: ${err.message}`, 'error');
  }
}

/**
 * Refresh API Health & Sidebar Dataset Status
 */
async function refreshSidebarStatus() {
  const apiStatusEl = document.getElementById('apiStatusPill');
  const dataCountsEl = document.getElementById('sidebarDataCounts');
  const dataBadgeEl = document.getElementById('sidebarDataBadge');

  try {
    const health = await apiRequest('/api/health');
    if (apiStatusEl) {
      apiStatusEl.innerHTML = `<span class="status-dot"></span> API Connected`;
      apiStatusEl.style.color = '#34d399';
    }
    if (dataCountsEl) {
      dataCountsEl.textContent = `${health.user_transactions_count} User • ${health.demo_transactions_count} Demo Txns`;
    }
    if (dataBadgeEl) {
      if (health.demo_transactions_count > 0 && health.user_transactions_count > 0) {
        dataBadgeEl.textContent = 'Hybrid Mode';
        dataBadgeEl.className = 'badge badge-info';
      } else if (health.demo_transactions_count > 0) {
        dataBadgeEl.textContent = 'Demo Active';
        dataBadgeEl.className = 'badge badge-demo';
      } else if (health.user_transactions_count > 0) {
        dataBadgeEl.textContent = 'User Data';
        dataBadgeEl.className = 'badge badge-user';
      } else {
        dataBadgeEl.textContent = 'Empty DB';
        dataBadgeEl.className = 'badge badge-neutral';
      }
    }
  } catch (err) {
    if (apiStatusEl) {
      apiStatusEl.innerHTML = `<span class="status-dot" style="background:#f43f5e;box-shadow:0 0 8px #f43f5e;"></span> API Offline`;
      apiStatusEl.style.color = '#fb7185';
    }
  }
}

/**
 * Initialize Mobile Sidebar Toggle & Shared Shell
 */
function initSharedShell() {
  configureChartDefaults();
  refreshSidebarStatus();

  const menuBtn = document.getElementById('mobileMenuBtn');
  const sidebar = document.getElementById('appSidebar');
  if (menuBtn && sidebar) {
    menuBtn.addEventListener('click', () => {
      sidebar.classList.toggle('open');
    });
  }

  // Close modals when clicking backdrop
  document.querySelectorAll('.modal-backdrop').forEach((backdrop) => {
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) {
        backdrop.classList.remove('open');
      }
    });
  });
}

function openModal(modalId) {
  const el = document.getElementById(modalId);
  if (el) el.classList.add('open');
}

function closeModal(modalId) {
  const el = document.getElementById(modalId);
  if (el) el.classList.remove('open');
}

document.addEventListener('DOMContentLoaded', initSharedShell);
