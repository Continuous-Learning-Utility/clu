// ===== FILE TREE =====
function renderFileTree(tree, depth) {
  if (depth === undefined) depth = 0;
  const container = document.getElementById('file-tree');
  if (depth === 0) container.innerHTML = '';
  renderTreeItems(tree, container, depth);
}

function renderTreeItems(items, container, depth) {
  for (const item of items) {
    const el = document.createElement('div');
    const ext = item.name.includes('.') ? item.name.split('.').pop().toLowerCase() : '';
    el.className = `tree-item ${item.type === 'directory' ? 'dir' : 'file'}${ext ? ' ext-' + ext : ''}`;
    el.style.setProperty('--depth', depth);
    el.dataset.name = item.name.toLowerCase();

    if (item.type === 'directory') {
      const count = countFiles(item);
      el.innerHTML = `<span class="icon">&#9658;</span>${escHtml(item.name)}<span class="count">${count}</span>`;
      container.appendChild(el);

      const childContainer = document.createElement('div');
      childContainer.style.display = 'none';
      childContainer.className = 'tree-children';
      container.appendChild(childContainer);

      el.onclick = () => {
        const open = childContainer.style.display !== 'none';
        childContainer.style.display = open ? 'none' : 'block';
        el.querySelector('.icon').innerHTML = open ? '&#9658;' : '&#9660;';
      };

      if (item.children) {
        renderTreeItems(item.children, childContainer, depth + 1);
      }
    } else {
      const ext2 = item.name.includes('.') ? item.name.split('.').pop().toUpperCase() : '';
      const icon = ext2 ? `<span class="file-ext">${escHtml(ext2)}</span>` : '&#128196;';
      el.innerHTML = `<span class="icon">${icon}</span>${escHtml(item.name)}`;
      el.onclick = () => viewFile(item.path);
      container.appendChild(el);
    }
  }
}

function countFiles(item) {
  if (item.type !== 'directory') return 1;
  return (item.children || []).reduce((sum, c) => sum + countFiles(c), 0);
}

function filterTree(query) {
  const q = query.toLowerCase();
  document.querySelectorAll('.tree-item').forEach(el => {
    if (!q) {
      el.style.display = '';
      return;
    }
    const name = el.dataset.name || '';
    el.style.display = name.includes(q) ? '' : 'none';
  });
}

async function viewFile(path) {
  try {
    const r = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
    const d = await r.json();
    if (d.error) { addMsg('error', escHtml(d.error)); return; }
    addMsg('tool-result',
      `<div class="msg-label">${escHtml(path)}<button class="copy-btn" onclick="copyText(this, ${escAttr(d.content)})">Copy</button></div>` +
      `<div class="result-content"><pre>${escHtml(d.content)}</pre></div>` +
      `<button class="expand-btn" onclick="toggleExpand(this)">Show more...</button>`
    );
  } catch (e) {
    addMsg('error', e.message);
  }
}
