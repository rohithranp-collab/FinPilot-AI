/**
 * FinPilot AI – AI Financial Assistant Controller (assistant.html)
 * Connects to GET /api/ai/status and POST /api/ai/chat
 */

let chatHistory = [];
let isSendingChat = false;

async function initAssistantPage() {
  await Promise.all([loadAIStatusAndSuggestions(), loadLiveContextSnapshot()]);
}

async function loadAIStatusAndSuggestions() {
  const statusBadge = document.getElementById('aiEngineStatusBadge');
  const modelBadge = document.getElementById('chatModelBadge');
  const banner = document.getElementById('aiConfigBanner');
  const bannerTitle = document.getElementById('aiConfigBannerTitle');
  const bannerText = document.getElementById('aiConfigBannerText');
  const suggestedContainer = document.getElementById('sidebarSuggestedList');

  try {
    const statusData = await apiRequest('/api/ai/status');
    if (modelBadge) {
      modelBadge.textContent = statusData.model || 'gemini-2.5-flash';
    }

    if (statusData.ai_configured) {
      if (statusBadge) {
        statusBadge.className = 'badge badge-success';
        statusBadge.textContent = `Gemini AI Connected (${statusData.model})`;
      }
      if (banner) {
        banner.style.display = 'none';
      }
    } else {
      if (statusBadge) {
        statusBadge.className = 'badge badge-warning';
        statusBadge.textContent = 'AI Not Configured (Local Data Mode)';
      }
      if (banner) {
        banner.style.display = 'block';
      }
      if (bannerTitle) {
        bannerTitle.textContent = 'AI Not Configured — Local Data-Driven Financial Engine Active';
      }
      if (bannerText) {
        bannerText.innerHTML =
          escapeHtml(statusData.message || 'GEMINI_API_KEY is not set in backend/.env.') +
          ' You can still ask questions below — FinPilot AI will compute personalized answers directly from your SQLite database.';
      }
    }

    if (suggestedContainer && Array.isArray(statusData.suggested_questions)) {
      suggestedContainer.innerHTML = statusData.suggested_questions
        .map(
          (q) => `
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          style="justify-content:flex-start;text-align:left;white-space:normal;line-height:1.35;padding:9px 12px;"
          onclick="askSuggestedQuestion('${escapeHtml(q).replace(/'/g, "\\'")}')"
        >
          💬 ${escapeHtml(q)}
        </button>
      `
        )
        .join('');
    }
  } catch (err) {
    if (statusBadge) {
      statusBadge.className = 'badge badge-danger';
      statusBadge.textContent = 'AI Status Error';
    }
  }
}

async function loadLiveContextSnapshot() {
  const container = document.getElementById('assistantContextSnapshot');
  if (!container) return;

  try {
    const [summary, forecast] = await Promise.all([
      apiRequest('/api/analytics/summary'),
      apiRequest('/api/predictions/cashflow?horizon=30'),
    ]);

    if (!summary.has_data) {
      container.innerHTML = `
        <div class="empty-state" style="padding:14px;">
          <p>No transactions in database yet. Click <strong>Seed Demo</strong> in the sidebar to populate sample data.</p>
        </div>
      `;
      return;
    }

    const h30 = (forecast.horizons && forecast.horizons['30_days']) || {};
    container.innerHTML = `
      <div style="display:flex;justify-content:space-between;padding:8px 10px;background:rgba(10,18,38,0.6);border-radius:8px;">
        <span style="color:var(--text-secondary);">Current Balance</span>
        <strong class="amount-cell" style="color:#38bdf8;">${formatINR(summary.total_balance)}</strong>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 10px;background:rgba(10,18,38,0.6);border-radius:8px;">
        <span style="color:var(--text-secondary);">Total Income / Expenses</span>
        <span class="amount-cell"><span class="amount-income">${formatCompactINR(summary.total_income)}</span> / <span class="amount-expense">${formatCompactINR(summary.total_expenses)}</span></span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 10px;background:rgba(10,18,38,0.6);border-radius:8px;">
        <span style="color:var(--text-secondary);">Savings Rate</span>
        <strong class="badge ${(summary.savings_rate_percent || 0) >= 20 ? 'badge-success' : 'badge-warning'}">${summary.savings_rate_percent || 0}%</strong>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 10px;background:rgba(10,18,38,0.6);border-radius:8px;">
        <span style="color:var(--text-secondary);">Financial Health Score</span>
        <strong>${summary.financial_health_score || 0}/100 (${escapeHtml(summary.health_label || 'Fair')})</strong>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 10px;background:rgba(10,18,38,0.6);border-radius:8px;">
        <span style="color:var(--text-secondary);">30-Day Forecast Balance</span>
        <strong class="amount-cell">${formatINR(h30.predicted_balance || summary.total_balance)}</strong>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 10px;background:rgba(10,18,38,0.6);border-radius:8px;">
        <span style="color:var(--text-secondary);">Flagged Anomalies</span>
        <span class="badge ${(summary.anomaly_count || 0) > 0 ? 'badge-danger' : 'badge-success'}">${summary.anomaly_count || 0} Alerts</span>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div class="empty-state" style="padding:12px;">Unable to load context snapshot.</div>`;
  }
}

function formatMarkdownToSafeHtml(rawText) {
  if (!rawText) return '';
  const escaped = escapeHtml(rawText);

  // Convert **bold** and `code`
  let formatted = escaped
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code style="background:rgba(59,130,246,0.16);padding:2px 6px;border-radius:4px;font-family:var(--font-mono);font-size:0.84em;">$1</code>');

  // Split into lines and build paragraphs / bullet lists
  const lines = formatted.split(/\r?\n/);
  let html = '';
  let inList = false;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (inList) {
        html += '</ul>';
        inList = false;
      }
      continue;
    }

    if (trimmed.startsWith('- ') || trimmed.startsWith('* ') || trimmed.startsWith('• ')) {
      if (!inList) {
        html += '<ul>';
        inList = true;
      }
      html += `<li>${trimmed.slice(2)}</li>`;
    } else if (trimmed.startsWith('### ')) {
      if (inList) {
        html += '</ul>';
        inList = false;
      }
      html += `<h4 style="margin:10px 0 4px;color:#93c5fd;">${trimmed.slice(4)}</h4>`;
    } else {
      if (inList) {
        html += '</ul>';
        inList = false;
      }
      html += `<p>${trimmed}</p>`;
    }
  }
  if (inList) {
    html += '</ul>';
  }
  return html;
}

function appendChatMessage(role, content, metaLabel = '') {
  const container = document.getElementById('chatMessagesContainer');
  if (!container) return;

  const wrapper = document.createElement('div');
  wrapper.className = `chat-msg ${role}`;

  const avatarLabel = role === 'user' ? 'YOU' : 'AI';
  const bodyHtml = role === 'user' ? `<p>${escapeHtml(content)}</p>` : formatMarkdownToSafeHtml(content);

  wrapper.innerHTML = `
    <div class="chat-avatar">${avatarLabel}</div>
    <div style="flex:1;min-width:0;">
      <div class="chat-bubble">${bodyHtml}</div>
      ${metaLabel ? `<div class="chat-meta">${escapeHtml(metaLabel)}</div>` : ''}
    </div>
  `;

  container.appendChild(wrapper);
  container.scrollTop = container.scrollHeight;
  return wrapper;
}

function askSuggestedQuestion(questionText) {
  const input = document.getElementById('chatInputBox');
  if (!input) return;
  input.value = questionText;
  sendChatQuestion(questionText);
}

async function handleChatSubmit(event) {
  event.preventDefault();
  const input = document.getElementById('chatInputBox');
  if (!input) return;
  const message = input.value.trim();
  if (!message) return;
  await sendChatQuestion(message);
}

async function sendChatQuestion(message) {
  if (isSendingChat) return;
  isSendingChat = true;

  const input = document.getElementById('chatInputBox');
  const sendBtn = document.getElementById('chatSendBtn');
  if (input) input.value = '';
  if (sendBtn) {
    sendBtn.disabled = true;
    sendBtn.textContent = 'Analyzing...';
  }

  appendChatMessage('user', message, 'You • Just now');

  const container = document.getElementById('chatMessagesContainer');
  const loadingEl = document.createElement('div');
  loadingEl.className = 'chat-msg assistant';
  loadingEl.innerHTML = `
    <div class="chat-avatar">AI</div>
    <div>
      <div class="chat-bubble" style="color:var(--text-secondary);">
        Analyzing your SQLite transactions, budgets, recurring bills, and cash-flow forecast...
      </div>
    </div>
  `;
  if (container) {
    container.appendChild(loadingEl);
    container.scrollTop = container.scrollHeight;
  }

  try {
    const res = await apiRequest('/api/ai/chat', {
      method: 'POST',
      body: JSON.stringify({
        message,
        history: chatHistory.slice(-6),
      }),
    });

    if (loadingEl && loadingEl.parentElement) {
      loadingEl.remove();
    }

    const sourceTag =
      res.source === 'gemini'
        ? `Google Gemini (${res.model}) • Live Database Grounded`
        : `${res.ai_notice || 'Local Data-Driven Engine'} • Live Database Grounded`;

    appendChatMessage('assistant', res.reply, sourceTag);

    chatHistory.push({ role: 'user', content: message });
    chatHistory.push({ role: 'assistant', content: res.reply });
  } catch (err) {
    if (loadingEl && loadingEl.parentElement) {
      loadingEl.remove();
    }
    appendChatMessage(
      'assistant',
      `I encountered an error while processing your request: ${err.message}`,
      'System Error'
    );
    showToast(err.message, 'error');
  } finally {
    isSendingChat = false;
    if (sendBtn) {
      sendBtn.disabled = false;
      sendBtn.textContent = 'Send Question →';
    }
    if (input) input.focus();
  }
}

function clearConversationHistory() {
  chatHistory = [];
  const container = document.getElementById('chatMessagesContainer');
  if (container) {
    container.innerHTML = `
      <div class="chat-msg assistant">
        <div class="chat-avatar">AI</div>
        <div>
          <div class="chat-bubble">
            <p><strong>Conversation cleared.</strong></p>
            <p>Ask any question about your spending, category budgets, recurring payments, or 7/30/90-day cash-flow forecast.</p>
          </div>
          <div class="chat-meta">FinPilot AI • Grounded in live database</div>
        </div>
      </div>
    `;
  }
  showToast('Chat history cleared.', 'info');
}

document.addEventListener('DOMContentLoaded', initAssistantPage);
