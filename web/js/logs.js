// ===== LOGS =====
function log(text, cls) {
  if (cls === undefined) cls = 'info';
  const logs = document.getElementById('logs');
  const time = new Date().toLocaleTimeString('en-US', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  const el = document.createElement('div');
  el.className = `log-entry ${cls}`;
  el.textContent = `[${time}] ${text}`;
  logs.appendChild(el);
  applyLogFilter(el);
  logs.scrollTop = logs.scrollHeight;
}

function setLogFilter(filter, btn) {
  currentLogFilter = filter;
  document.querySelectorAll('.log-filter button').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  document.querySelectorAll('.log-entry').forEach(el => applyLogFilter(el));
}

function applyLogFilter(el) {
  if (currentLogFilter === 'all') { el.style.display = ''; return; }
  el.style.display = el.classList.contains(currentLogFilter) ? '' : 'none';
}
