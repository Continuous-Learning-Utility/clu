// ===== GLOBAL STATE =====
let ws = null;
let isRunning = false;
let lastSessionId = null;
let autoScroll = true;
let currentLogFilter = 'all';

// ===== UTILITY FUNCTIONS =====
function escHtml(s) {
  if (typeof s !== 'string') s = String(s);
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

function escAttr(s) {
  return '`' + s.replace(/\\/g, '\\\\').replace(/`/g, '\\`') + '`';
}

function truncate(s, n) {
  return s.length > n ? s.substring(0, n) + '...' : s;
}

function formatMarkdown(text) {
  if (!text) return '';
  let html = escHtml(text);
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre>$2</pre>');
  html = html.replace(/`([^`]+)`/g, '<code style="background:rgba(0,0,0,0.3);padding:2px 4px;border-radius:3px;">$1</code>');
  html = html.replace(/^### (.+)$/gm, '<strong style="font-size:14px;">$1</strong>');
  html = html.replace(/^## (.+)$/gm, '<strong style="font-size:15px;">$1</strong>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/^- (.+)$/gm, '&bull; $1');
  html = html.replace(/\n/g, '<br>');
  return html;
}

function copyText(btn, text) {
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = 'Copy';
      btn.classList.remove('copied');
    }, 1500);
  });
}

function toggleExpand(btn) {
  const content = btn.previousElementSibling;
  if (!content) return;
  const expanded = content.classList.toggle('expanded');
  btn.textContent = expanded ? 'Show less' : 'Show more...';
}

function showOverlay(title, text) {
  document.getElementById('overlay-title').textContent = title;
  document.getElementById('overlay-text').textContent = text;
  document.getElementById('overlay').classList.remove('hidden');
}

function hideOverlay() {
  document.getElementById('overlay').classList.add('hidden');
}
