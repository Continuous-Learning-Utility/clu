// ===== SCHEDULES UI =====

function initSchedules() {
  loadSchedules();
}

async function loadSchedules() {
  try {
    const r = await fetch('/api/schedules');
    const d = await r.json();
    renderSchedules(d);
  } catch (e) {
    console.error('Failed to load schedules:', e);
  }
}

function renderSchedules(data) {
  const el = document.getElementById('schedules-content');
  if (!el) return;

  const schedules = data.schedules || [];

  if (!schedules.length) {
    el.innerHTML = '<div class="empty-state">No schedules defined</div>';
    return;
  }

  const html = schedules.map(s => {
    const nextRun = s.next_run ? new Date(s.next_run).toLocaleString() : 'N/A';
    const lastRun = s.last_run ? new Date(s.last_run * 1000).toLocaleTimeString() : 'Never';
    const statusCls = s.enabled ? 'ok' : 'err';
    const statusText = s.enabled ? 'Active' : 'Disabled';

    return `<div class="schedule-item">
      <div class="schedule-header">
        <span class="schedule-id">${escHtml(s.id)}</span>
        <span class="badge sm ${statusCls}">${statusText}</span>
      </div>
      <div class="schedule-cron" title="${escHtml(s.description || '')}">${escHtml(s.cron)}</div>
      <div class="schedule-meta">
        <span>Template: ${escHtml(s.task_template)}</span>
        <span>Runs: ${s.run_count || 0}</span>
      </div>
      <div class="schedule-meta">
        <span>Next: ${nextRun}</span>
        <span>Last: ${lastRun}</span>
      </div>
      ${s.last_error ? `<div class="task-error">${escHtml(s.last_error)}</div>` : ''}
      <div class="task-actions">
        <button class="btn sm" onclick="toggleSchedule('${escHtml(s.id)}')">${s.enabled ? 'Disable' : 'Enable'}</button>
        <button class="btn sm" onclick="triggerSchedule('${escHtml(s.id)}')" ${!s.enabled ? 'disabled' : ''}>Run Now</button>
        <button class="btn sm danger" onclick="deleteSchedule('${escHtml(s.id)}')">Delete</button>
      </div>
    </div>`;
  }).join('');

  el.innerHTML = `
    <div class="schedule-summary">
      <span>${data.active_schedules || 0} active / ${data.total_schedules || 0} total</span>
      <button class="btn sm" onclick="reloadSchedules()">Reload Config</button>
    </div>
    ${html}
  `;
}

async function toggleSchedule(id) {
  await fetch(`/api/schedules/${id}/toggle`, { method: 'POST' });
  loadSchedules();
}

async function triggerSchedule(id) {
  try {
    const r = await fetch(`/api/schedules/${id}/trigger`, { method: 'POST' });
    const d = await r.json();
    if (d.ok) {
      log(`Schedule "${id}" triggered → task #${d.task_id}`, 'ok');
      loadSchedules();
      loadTasks();
    } else {
      log('Trigger failed: ' + (d.error || ''), 'err');
    }
  } catch (e) {
    log('Trigger error: ' + e.message, 'err');
  }
}

async function deleteSchedule(id) {
  if (!confirm(`Delete schedule "${id}"?`)) return;
  await fetch(`/api/schedules/${id}`, { method: 'DELETE' });
  loadSchedules();
}

async function reloadSchedules() {
  const r = await fetch('/api/schedules/reload', { method: 'POST' });
  const d = await r.json();
  log(`Schedules reloaded: ${d.count || 0} loaded`, 'ok');
  loadSchedules();
}
