// ===== SKILLS REGISTRY CONFIG =====

async function syncRegistryNow() {
  const btn = document.getElementById('registry-sync-btn');
  const status = document.getElementById('registry-status-text');
  if (btn) btn.disabled = true;
  if (status) status.textContent = 'Syncing...';
  try {
    const r = await fetch('/api/skills/registry/sync', { method: 'POST' });
    const d = await r.json();
    if (d.errors && d.errors.length) {
      log('Registry sync error: ' + d.errors[0], 'err');
      if (status) status.textContent = 'Sync failed';
    } else {
      const added = d.added ? d.added.length : 0;
      const updated = d.updated ? d.updated.length : 0;
      const msg = `+${added} added, ~${updated} updated`;
      log('Registry synced: ' + msg, 'ok');
      if (status) status.textContent = 'Synced: ' + msg;
      loadRegistryStatus();
    }
  } catch (e) {
    log('Registry sync failed: ' + e.message, 'err');
    if (status) status.textContent = 'Sync failed';
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function loadRegistryStatus() {
  try {
    const r = await fetch('/api/skills/registry/status');
    const d = await r.json();
    const status = document.getElementById('registry-status-text');
    if (!status) return;
    const installed = d.installed_count || 0;
    let lastSync = '';
    if (d.last_sync) {
      const dt = new Date(d.last_sync * 1000);
      lastSync = ' · Last sync: ' + dt.toLocaleString();
    }
    status.textContent = `${installed} installed${lastSync}`;
  } catch (e) {
    // Non-critical — status line stays empty
  }
}
