// ===== ALERTS / NOTIFICATION CENTER =====

let _alertsInterval = null;

function initAlerts() {
  loadAlerts();
  if (_alertsInterval) clearInterval(_alertsInterval);
  _alertsInterval = setInterval(updateAlertBadge, 15000);
  updateAlertBadge();
}

async function loadAlerts() {
  try {
    const r = await fetch('/api/alerts?limit=30');
    const d = await r.json();
    renderAlerts(d.alerts || [], d.stats || {});
  } catch (e) {
    console.error('Failed to load alerts:', e);
  }
}

function renderAlerts(alerts, stats) {
  const el = document.getElementById('alerts-content');
  if (!el) return;

  const unread = stats.unread || 0;

  if (!alerts.length) {
    el.innerHTML = '<div class="empty-state">No alerts</div>';
    return;
  }

  const html = alerts.map(a => {
    const cls = a.level || 'info';
    const icon = cls === 'error' ? '&#10007;' : cls === 'warning' ? '&#9888;' : '&#9432;';
    const time = a.timestamp ? new Date(a.timestamp * 1000).toLocaleString() : '';
    const readCls = a.read ? 'read' : 'unread';

    return `<div class="alert-item ${cls} ${readCls}">
      <div class="alert-header">
        <span class="alert-icon ${cls}">${icon}</span>
        <span class="alert-source">${escHtml(a.source || '')}</span>
        <span class="alert-time">${time}</span>
        ${!a.read ? `<button class="btn sm" onclick="markAlertRead(${a.id})">Read</button>` : ''}
        <button class="btn sm danger" onclick="deleteAlert(${a.id})">&times;</button>
      </div>
      <div class="alert-message">${escHtml(a.message || '')}</div>
    </div>`;
  }).join('');

  el.innerHTML = `
    <div class="alerts-toolbar">
      <span>${unread} unread / ${stats.total || 0} total</span>
      <div>
        ${unread > 0 ? '<button class="btn sm" onclick="markAllAlertsRead()">Mark all read</button>' : ''}
        <button class="btn sm danger" onclick="clearAllAlerts()">Clear all</button>
      </div>
    </div>
    ${html}
  `;
}

async function markAlertRead(id) {
  await fetch(`/api/alerts/${id}/read`, { method: 'POST' });
  loadAlerts();
  updateAlertBadge();
}

async function markAllAlertsRead() {
  await fetch('/api/alerts/read-all', { method: 'POST' });
  loadAlerts();
  updateAlertBadge();
}

async function deleteAlert(id) {
  await fetch(`/api/alerts/${id}`, { method: 'DELETE' });
  loadAlerts();
}

async function clearAllAlerts() {
  if (!confirm('Clear all alerts?')) return;
  await fetch('/api/alerts', { method: 'DELETE' });
  loadAlerts();
  updateAlertBadge();
}

async function updateAlertBadge() {
  try {
    const r = await fetch('/api/alerts?unread_only=true&limit=0');
    const d = await r.json();
    const count = d.stats?.unread || 0;
    const badge = document.getElementById('alerts-badge');
    if (badge) {
      badge.textContent = count > 0 ? count : '';
      badge.style.display = count > 0 ? '' : 'none';
    }
  } catch (e) {}
}
