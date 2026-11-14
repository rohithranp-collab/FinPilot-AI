/**
 * FinPilot AI – Transactions Management & CSV Import Controller (transactions.html)
 */

let currentTransactionsList = [];

async function loadTransactionsPage() {
  const search = (document.getElementById('filterSearch')?.value || '').trim();
  const type = document.getElementById('filterType')?.value || '';
  const category = document.getElementById('filterCategory')?.value || '';
  const dataSource = document.getElementById('filterDataSource')?.value || '';
  const startDate = document.getElementById('filterStartDate')?.value || '';
  const endDate = document.getElementById('filterEndDate')?.value || '';

  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (type && type !== 'all') params.set('type', type);
  if (category && category !== 'All') params.set('category', category);
  if (dataSource && dataSource !== 'all') params.set('data_source', dataSource);
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);
  params.set('limit', '500');

  try {
    const res = await apiRequest(`/api/transactions?${params.toString()}`);
    currentTransactionsList = res.transactions || [];
    renderTransactionsSummary(res);
    renderTransactionsTable(currentTransactionsList);
  } catch (err) {
    showToast(`Failed to load transactions: ${err.message}`, 'error');
  }
}

function renderTransactionsSummary(res) {
  const fs = res.filtered_summary || {};
  const dbInfo = res.dataset_breakdown || {};

  const countEl = document.getElementById('txFilteredCount');
  const incEl = document.getElementById('txFilteredIncome');
  const expEl = document.getElementById('txFilteredExpense');
  const netEl = document.getElementById('txFilteredNet');

  if (countEl) {
    countEl.textContent = `${res.total || 0} Transactions`;
  }
  const subCountEl = document.getElementById('txDatasetSub');
  if (subCountEl) {
    subCountEl.textContent = `${dbInfo.user_transactions || 0} User-Entered • ${dbInfo.demo_transactions || 0} Demo`;
  }
  if (incEl) incEl.textContent = formatINR(fs.income || 0);
  if (expEl) expEl.textContent = formatINR(fs.expense || 0);
  if (netEl) netEl.textContent = formatINR(fs.net || 0);
}

function renderTransactionsTable(items) {
  const tbody = document.getElementById('transactionsTableBody');
  if (!tbody) return;

  if (!items.length) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="empty-state">
          <h4>No Matching Transactions Found</h4>
          <p>Try adjusting your search filters, add a new transaction, import a CSV file, or seed demo data.</p>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = items
    .map(
      (tx) => `
    <tr>
      <td style="white-space:nowrap;">${formatDate(tx.date)}</td>
      <td>
        <div style="font-weight:600;">${escapeHtml(tx.description)}</div>
        <div style="font-size:0.74rem;color:var(--text-secondary);margin-top:2px;">
          ${escapeHtml(tx.categorization_reason || '')}
        </div>
      </td>
      <td>
        <span class="badge badge-neutral" style="border-color:${getCategoryColor(tx.category)}66;color:#f1f5f9;">
          ${escapeHtml(tx.category)}
        </span>
        ${tx.auto_categorized ? '<span class="badge badge-info" style="margin-left:4px;font-size:0.66rem;">AI Auto</span>' : ''}
      </td>
      <td>
        <span class="badge ${tx.type === 'income' ? 'badge-income' : 'badge-expense'}">
          ${tx.type === 'income' ? 'INCOME' : 'EXPENSE'}
        </span>
      </td>
      <td>
        <span style="font-size:0.8rem;color:var(--text-secondary);">${escapeHtml(tx.payment_method)}</span>
        <div>
          <span class="badge ${tx.is_demo ? 'badge-demo' : 'badge-user'}" style="font-size:0.66rem;margin-top:3px;">
            ${tx.is_demo ? 'Demo Data' : 'User Data'}
          </span>
        </div>
      </td>
      <td class="amount-cell ${tx.type === 'income' ? 'amount-income' : 'amount-expense'}" style="white-space:nowrap;">
        ${tx.type === 'income' ? '+' : '-'}${formatINR(tx.amount, true)}
      </td>
      <td style="white-space:nowrap;">
        <div style="display:flex;gap:6px;">
          <button class="btn btn-secondary btn-xs" onclick="openEditTransactionModal(${tx.id})">Edit</button>
          <button class="btn btn-danger btn-xs" onclick="deleteTransactionById(${tx.id})">Delete</button>
        </div>
      </td>
    </tr>
  `
    )
    .join('');
}

function resetTransactionFilters() {
  if (document.getElementById('filterSearch')) document.getElementById('filterSearch').value = '';
  if (document.getElementById('filterType')) document.getElementById('filterType').value = 'all';
  if (document.getElementById('filterCategory')) document.getElementById('filterCategory').value = 'All';
  if (document.getElementById('filterDataSource')) document.getElementById('filterDataSource').value = 'all';
  if (document.getElementById('filterStartDate')) document.getElementById('filterStartDate').value = '';
  if (document.getElementById('filterEndDate')) document.getElementById('filterEndDate').value = '';
  loadTransactionsPage();
}

async function handleLiveCategoryPreview() {
  const desc = (document.getElementById('txFormDesc')?.value || '').trim();
  const type = document.getElementById('txFormType')?.value || 'expense';
  const amount = parseFloat(document.getElementById('txFormAmount')?.value || '0') || null;
  const previewBox = document.getElementById('txAiCategoryPreview');
  if (!previewBox) return;

  if (desc.length < 2) {
    previewBox.innerHTML = 'AI Categorizer Ready: Type a merchant or description (e.g., "Swiggy", "Apollo Pharmacy", "Infosys Salary") to see live rule/ML classification.';
    return;
  }

  try {
    const res = await apiRequest('/api/transactions/categorize-preview', {
      method: 'POST',
      body: JSON.stringify({ description: desc, type, amount }),
    });
    previewBox.innerHTML = `<strong>AI Suggested Category: ${escapeHtml(res.category)}</strong> (${escapeHtml(res.method)})<br/><span>${escapeHtml(res.reason)}</span>`;
  } catch (_) {}
}

function openCreateTransactionModal() {
  document.getElementById('txModalTitle').textContent = 'Add New Transaction';
  document.getElementById('txFormId').value = '';
  document.getElementById('txFormDate').value = new Date().toISOString().slice(0, 10);
  document.getElementById('txFormAmount').value = '';
  document.getElementById('txFormDesc').value = '';
  document.getElementById('txFormType').value = 'expense';
  document.getElementById('txFormCategory').value = 'Auto';
  document.getElementById('txFormMethod').value = 'UPI / Bank';
  const previewBox = document.getElementById('txAiCategoryPreview');
  if (previewBox) {
    previewBox.textContent = 'Leave Category on "Auto (AI Categorization)" to let FinPilot AI automatically classify and explain your transaction.';
  }
  openModal('transactionFormModal');
}

function openEditTransactionModal(txId) {
  const tx = currentTransactionsList.find((t) => t.id === txId);
  if (!tx) return;

  document.getElementById('txModalTitle').textContent = `Edit Transaction #${tx.id}`;
  document.getElementById('txFormId').value = String(tx.id);
  document.getElementById('txFormDate').value = tx.date;
  document.getElementById('txFormAmount').value = tx.amount;
  document.getElementById('txFormDesc').value = tx.description;
  document.getElementById('txFormType').value = tx.type;
  document.getElementById('txFormCategory').value = tx.category;
  document.getElementById('txFormMethod').value = tx.payment_method || 'UPI / Bank';

  const previewBox = document.getElementById('txAiCategoryPreview');
  if (previewBox) {
    previewBox.textContent = tx.categorization_reason || 'Select "Auto" to re-run AI categorization.';
  }
  openModal('transactionFormModal');
}

async function submitTransactionForm(event) {
  event.preventDefault();
  const txId = document.getElementById('txFormId').value;
  const dateVal = document.getElementById('txFormDate').value;
  const amountVal = parseFloat(document.getElementById('txFormAmount').value);
  const descVal = document.getElementById('txFormDesc').value.trim();
  const typeVal = document.getElementById('txFormType').value;
  const catVal = document.getElementById('txFormCategory').value;
  const methodVal = document.getElementById('txFormMethod').value;

  const payload = {
    date: dateVal,
    amount: amountVal,
    description: descVal,
    type: typeVal,
    category: catVal === 'Auto' ? 'Auto' : catVal,
    payment_method: methodVal,
    is_demo: false,
  };

  try {
    if (txId) {
      const res = await apiRequest(`/api/transactions/${txId}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      showToast(`Updated Transaction #${txId} → ${res.transaction.category}`, 'success');
    } else {
      const res = await apiRequest('/api/transactions', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      showToast(
        `Transaction Added: ${res.transaction.description} (${formatINR(res.transaction.amount)}) → ${res.transaction.category}`,
        'success'
      );
    }
    closeModal('transactionFormModal');
    await refreshSidebarStatus();
    await loadTransactionsPage();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function deleteTransactionById(txId) {
  try {
    await apiRequest(`/api/transactions/${txId}`, { method: 'DELETE' });
    showToast(`Transaction #${txId} deleted.`, 'info');
    await refreshSidebarStatus();
    await loadTransactionsPage();
  } catch (err) {
    showToast(`Failed to delete transaction: ${err.message}`, 'error');
  }
}

/**
 * CSV Import Handler (Supports both File Upload and Raw CSV Text Paste)
 */
async function submitCsvImport(event) {
  event.preventDefault();
  const fileInput = document.getElementById('csvFileInput');
  const rawTextInput = document.getElementById('csvRawTextInput');

  try {
    let res;
    if (fileInput && fileInput.files && fileInput.files.length > 0) {
      const formData = new FormData();
      formData.append('file', fileInput.files[0]);
      res = await apiRequest('/api/transactions/import', {
        method: 'POST',
        body: formData,
      });
    } else if (rawTextInput && rawTextInput.value.trim()) {
      res = await apiRequest('/api/transactions/import', {
        method: 'POST',
        body: JSON.stringify({ csv_content: rawTextInput.value.trim() }),
      });
    } else {
      showToast('Please select a CSV file or paste CSV rows first.', 'error');
      return;
    }

    closeModal('csvImportModal');
    if (fileInput) fileInput.value = '';
    if (rawTextInput) rawTextInput.value = '';

    showToast(
      `Imported ${res.imported_count} transactions (${res.skipped_count} skipped)!`,
      'success'
    );
    await refreshSidebarStatus();
    await loadTransactionsPage();
  } catch (err) {
    showToast(`CSV Import Error: ${err.message}`, 'error');
  }
}

function loadSampleCsvIntoTextarea() {
  const today = new Date().toISOString().slice(0, 10);
  const sampleCsv = [
    'date,amount,description,type,category,payment_method',
    `${today},45000,Client Consulting Milestone Payment,income,Auto,NEFT`,
    `${today},780,Swiggy Gourmet Dinner Order,expense,Auto,UPI`,
    `${today},2450,IndianOil Fuel Station Petrol,expense,Auto,UPI`,
    `${today},1499,Amazon Wireless Keyboard & Mouse,expense,Auto,Credit Card`,
    `${today},950,Apollo Pharmacy Health Supplements,expense,Auto,UPI`,
  ].join('\n');

  const rawTextInput = document.getElementById('csvRawTextInput');
  if (rawTextInput) {
    rawTextInput.value = sampleCsv;
    showToast('Loaded 5 sample Indian Rupee CSV rows with Auto AI categorization!', 'info');
  }
}

function exportFilteredTransactionsCsv() {
  if (!currentTransactionsList.length) {
    showToast('No transactions to export.', 'error');
    return;
  }
  const headers = ['id', 'date', 'amount', 'description', 'type', 'category', 'payment_method', 'is_demo'];
  const csvRows = [
    headers.join(','),
    ...currentTransactionsList.map((t) =>
      [
        t.id,
        t.date,
        t.amount,
        `"${String(t.description || '').replace(/"/g, '""')}"`,
        t.type,
        t.category,
        `"${String(t.payment_method || '').replace(/"/g, '""')}"`,
        t.is_demo,
      ].join(',')
    ),
  ];

  const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `finpilot_transactions_${new Date().toISOString().slice(0, 10)}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('transactionsTableBody')) {
    loadTransactionsPage();
  }
});
