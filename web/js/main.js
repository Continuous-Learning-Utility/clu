// ===== API CALLS =====
async function checkStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();

    if (d.provider) {
      if (d.provider.connected) {
        const label = d.provider.model ? d.provider.model.split('/').pop() : d.provider.name;
        setBadge('badge-provider', `LLM: ${label}`, 'ok');
      } else {
        setBadge('badge-provider', 'LLM: offline', 'err');
      }
      providerStore.restore(d.provider);
    }

    if (d.project && d.project.valid) {
      setBadge('badge-project', `${d.project.source_files || d.project.cs_files} files`, 'ok');
      document.getElementById('project-path').value = d.project.path;
      refreshFiles();
    } else if (d.project && d.project.path) {
      setBadge('badge-project', 'Project: invalid', 'warn');
    }
    loadSessions();
  } catch (e) {
    log('Status check failed: ' + e.message, 'err');
  }
}

async function browseProject() {
  try {
    const r = await fetch('/api/browse/folder', { method: 'POST' });
    const d = await r.json();
    if (d.ok && d.path) {
      document.getElementById('project-path').value = d.path;
      setProject();
    }
  } catch (e) {
    log('Browse failed: ' + e.message, 'err');
  }
}

async function setProject() {
  const path = document.getElementById('project-path').value.trim();
  if (!path) return;
  try {
    const r = await fetch('/api/project', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path}),
    });
    const d = await r.json();
    if (d.error) {
      addMsg('error', escHtml(d.error));
      setBadge('badge-project', 'Project: err', 'err');
    } else {
      log(`Project: ${path}`, 'ok');
      checkStatus();
    }
  } catch (e) {
    addMsg('error', 'Error: ' + e.message);
  }
}

async function refreshFiles() {
  try {
    const r = await fetch('/api/files');
    const d = await r.json();
    if (d.error) return;
    renderFileTree(d.tree);
  } catch (e) {}
}

// ===== KEYBOARD SHORTCUTS =====
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeAllPanels();
  }
});

// ===== INIT =====
connectWS();
// Initialize alert badge (runs independently of tab selection)
setTimeout(updateAlertBadge, 2000);
