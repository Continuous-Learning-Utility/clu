// ===== SESSIONS =====
async function loadSessions() {
  try {
    const r = await fetch('/api/sessions');
    const d = await r.json();
    const el = document.getElementById('sessions-list');
    if (!d.sessions || d.sessions.length === 0) {
      el.innerHTML = '<div style="color:var(--text2);font-size:11px;">No sessions</div>';
      return;
    }
    el.innerHTML = d.sessions.slice(0, 10).map(s => {
      const date = s.created ? new Date(s.created).toLocaleString('en-US', {day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'}) : '?';
      const task = escHtml(s.task || '').substring(0, 40);
      return `<div class="session-item">
        <div class="session-info" onclick="resumeSession('${s.id}')">
          <span class="session-id">${s.id}</span> <span class="session-date">${date}</span>
          <span class="session-task">${task}</span>
        </div>
        <button class="session-delete" onclick="deleteSession('${s.id}')" title="Delete">&#10005;</button>
      </div>`;
    }).join('');
  } catch (e) {
    log('Sessions error: ' + e.message, 'err');
  }
}

function resumeSession(sessionId) {
  if (isRunning) return;
  lastSessionId = sessionId;
  addMsg('system-msg', `Session ${sessionId} selected for resume.`);
  document.getElementById('task-input').focus();
}

async function deleteSession(sessionId) {
  try {
    await fetch(`/api/sessions/${sessionId}`, {method: 'DELETE'});
    log(`Session ${sessionId} deleted`, 'ok');
    loadSessions();
  } catch (e) {}
}

async function updateBudgetConfig() {
  const iterations = document.getElementById('cfg-iterations').value;
  const tokens = document.getElementById('cfg-tokens').value;
  const body = {};
  if (iterations) body.max_iterations = parseInt(iterations);
  if (tokens) body.max_total_tokens = parseInt(tokens);
  if (Object.keys(body).length === 0) return;

  try {
    const r = await fetch('/api/config/budget', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const d = await r.json();
    if (d.ok) {
      log(`Budget: ${d.max_iterations} iter, ${(d.max_total_tokens/1000).toFixed(0)}K tokens`, 'ok');
      document.getElementById('cfg-iterations').value = '';
      document.getElementById('cfg-tokens').value = '';
    }
  } catch (e) {
    log('Budget error: ' + e.message, 'err');
  }
}
