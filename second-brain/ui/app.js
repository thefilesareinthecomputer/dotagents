// second-brain UI - 2026 Glassmorphism Chat Interface
// Uses marked.js for markdown + mermaid.js for diagrams

const API_BASE = '';
let eventSource = null;
let mermaidModule = null;
let currentConversationId = null;
let conversations = [];
let conversationListExpanded = false;
let conversationTotalCount = 0;
const CONVERSATION_PAGE_SIZE = 5;

// Configure marked.js
function initMarkdown() {
  if (typeof marked !== 'undefined') {
    const renderer = new marked.Renderer();
    renderer.code = function(code, language) {
      // marked v5+ passes one token object; v4 passed (string, lang).
      if (code && typeof code === 'object') {
        language = code.lang;
        code = code.text;
      }
      if (language === 'mermaid') {
        return `<pre class="mermaid">${code}</pre>`;
      }
      if (language && typeof hljs !== 'undefined' && hljs.getLanguage(language)) {
        const highlighted = hljs.highlight(code, { language }).value;
        return `<pre><code class="hljs ${language}">${highlighted}</code></pre>`;
      }
      if (typeof hljs !== 'undefined') {
        const highlighted = hljs.highlightAuto(code).value;
        return `<pre><code class="hljs">${highlighted}</code></pre>`;
      }
      return `<pre><code>${code}</code></pre>`;
    };
    marked.setOptions({
      breaks: true,
      gfm: true,
      headerIds: false,
      mangle: false,
      renderer: renderer,
    });
  }
}

// --- Markdown rendering: every model-authored string goes through here.
//
// Agent replies are untrusted text and markdown passes raw HTML straight
// through, so rendering one with marked.parse() alone puts live markup in
// the UI's origin - same-origin with a local API that seats agents,
// rewrites settings and deletes conversations. An e2e test plants
// `<img src=x onerror=...>` in a seat reply and asserts it never fires.
//
// The cleaner is an ALLOWLIST, matching the seat grant doctrine: only the
// elements and attributes marked itself emits survive, and anything
// unrecognized is unwrapped or dropped. That way a tag nobody thought of
// is inert by default, rather than dangerous until someone adds it to a
// blocklist. Event-handler attributes need no special case - they are
// simply not on the list.
const MD_ALLOWED_TAGS = new Set([
  'P', 'BR', 'HR', 'EM', 'STRONG', 'DEL', 'CODE', 'PRE', 'BLOCKQUOTE',
  'UL', 'OL', 'LI', 'A', 'SPAN', 'DIV',
  'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
  'TABLE', 'THEAD', 'TBODY', 'TR', 'TH', 'TD',
]);
// class carries syntax highlighting (hljs) and the mermaid hook.
const MD_ALLOWED_ATTRS = {
  A: ['href', 'title'], CODE: ['class'], PRE: ['class'], SPAN: ['class'],
  DIV: ['class'], TH: ['align'], TD: ['align'],
};
// Removed with their contents; unwrapping these would keep the payload.
const MD_DROP_WHOLE = new Set([
  'SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'LINK', 'META', 'BASE',
  'FORM', 'INPUT', 'BUTTON', 'TEXTAREA', 'SELECT', 'SVG', 'MATH', 'IMG',
  'AUDIO', 'VIDEO', 'SOURCE', 'TRACK', 'CANVAS', 'TEMPLATE',
]);

function sanitizeMarkdownNode(parent) {
  Array.from(parent.children).forEach((el) => {
    if (MD_DROP_WHOLE.has(el.tagName)) { el.remove(); return; }
    if (!MD_ALLOWED_TAGS.has(el.tagName)) {
      sanitizeMarkdownNode(el);            // clean before unwrapping
      el.replaceWith(...el.childNodes);    // keep the text, drop the tag
      return;
    }
    const allowed = MD_ALLOWED_ATTRS[el.tagName] || [];
    Array.from(el.attributes).forEach((attr) => {
      if (!allowed.includes(attr.name.toLowerCase())) {
        el.removeAttribute(attr.name);
      }
    });
    if (el.tagName === 'A') {
      // javascript: and data: URLs are script delivery; only navigable
      // schemes and in-page or app-relative targets survive.
      const href = (el.getAttribute('href') || '').trim();
      if (!/^(https?:\/\/|mailto:|#|\/)/i.test(href)) {
        el.removeAttribute('href');
      } else if (/^https?:\/\//i.test(href)) {
        el.setAttribute('target', '_blank');
        el.setAttribute('rel', 'noopener noreferrer');
      }
    }
    sanitizeMarkdownNode(el);
  });
}

// Vault paths open through ONE delegated listener reading a data-path
// attribute, never through an inline onclick built by interpolation.
// The old form put the path inside a JS string inside an HTML attribute,
// where escaping has to be correct for two nested grammars at once - a
// filename with an apostrophe broke out and executed, and vault
// filenames are agent-writable. A data attribute is inert by
// construction: the path is read back as a value, never parsed as code.
// Every other control follows the same principle: markup declares WHAT a
// control does in a data-action attribute, and this map is the only place
// that says HOW. No behavior is ever spelled as script inside an
// attribute, which is what lets the CSP in index.html forbid inline
// script outright - with no inline handler anywhere in the app, an
// injected one cannot run even if a sanitizer misses it.
const CLICK_ACTIONS = {
  'new-conversation': () => createNewConversation(),
  'switch-conversation': (el) => switchConversation(el.dataset.id),
  'delete-conversation': (el) => deleteConversation(el.dataset.id),
  'toggle-conversation-list': () => toggleConversationListExpanded(),
  'toggle-graph-hud': () => toggleGraphHUD(),
  'toggle-mission': () => toggleMissionControl(),
  'toggle-section': (el) => toggleSection(el),
  'toggle-folder': (el) => toggleFolder(el),
  'add-seat': () => addSeat(),
  'remove-seat': (el) => removeSeat(el.dataset.id),
  'seat-policy': (el) => toggleSeatPolicy(el.dataset.id),
  'close-file-viewer': () => closeFileViewer(),
  'cancel-round': () => cancelRound(),
  'copy-message': (el) => copyMessage(el),
  'toggle-rail': () => toggleRail(),
  'jump-to-feed': (el) => jumpToFeed(el.dataset.turn),
  'jump-to-turn': (el) => jumpToTurn(el.dataset.turn),
  // Thinking and tool rows collapse by class on their own container.
  // closest() rather than parentElement so the toggle survives a change
  // to the header's nesting. A tool result renders on first expand, not
  // when it arrives, so a busy turn costs nothing until someone looks.
  'toggle-bubble': (el) => {
    const bubble = el.closest('.thinking-bubble, .tool-call-bubble');
    if (!bubble) return;
    const opening = bubble.classList.toggle('collapsed') === false;
    if (opening && bubble._result !== undefined) {
      const resultEl = bubble.querySelector('.tool-bubble-content');
      resultEl.insertAdjacentHTML('beforeend', renderMarkdown(bubble._result));
      renderMermaidDiagrams(bubble);
      delete bubble._result;
    }
  },
};

document.addEventListener('click', (event) => {
  // The folder-graph button sits inside a folder row, so it claims the
  // click first and stops the row from also toggling. This branch stays
  // ahead of the data-action dispatch below: the button carries no
  // action of its own, so the dispatch would otherwise walk up to the
  // folder header and toggle the folder instead.
  const graphBtn = event.target.closest('.folder-graph-btn[data-graph-path]');
  if (graphBtn) {
    event.stopPropagation();
    viewFolderGraph(graphBtn.dataset.graphPath);
    return;
  }
  // The NEAREST data-action wins, which is what keeps a delete button
  // inside a conversation row from also switching to that conversation.
  const actionEl = event.target.closest('[data-action]');
  if (actionEl) {
    // hasOwn, not a bare index: every Object.prototype member is truthy, so
    // an action named after one (constructor, toString) would both dispatch
    // nonsense and swallow the data-path fallback below.
    const name = actionEl.dataset.action;
    const run = Object.hasOwn(CLICK_ACTIONS, name) ? CLICK_ACTIONS[name] : null;
    if (run) {
      run(actionEl);
      return;
    }
  }
  const target = event.target.closest(
    '.file-item[data-path], .search-result[data-path], li[data-path]');
  if (target) loadFile(target.dataset.path);
});

// Mermaid renders SVG, which the markdown allowlist never sees - the
// diagram is replaced after that walk has run. SVG carries its own script
// surface (event handlers, xlink:href, <script>, <foreignObject>), so it
// gets its own scrub: drop active elements, strip every on* handler, and
// remove any href whose scheme is not navigable.
function sanitizeRenderedSvg(root) {
  root.querySelectorAll('script, foreignObject, iframe, object, embed')
    .forEach((el) => el.remove());
  // Mermaid emits a <style> block, and a diagram's own `%%{init:
  // {'themeCSS': ...}}%%` directive writes into it. That is model-authored
  // CSS, and `url(http://...)` in it makes live outbound requests from the
  // UI's origin - a beacon out of a local-only app, verified 2026-08-29.
  // Only in-document and data: URLs survive.
  root.querySelectorAll('style').forEach((el) => {
    el.textContent = (el.textContent || '').replace(
      /url\(\s*(['"]?)([^)'"]*)\1\s*\)/gi,
      (whole, _quote, target) =>
        /^(#|data:)/i.test(target.trim()) ? whole : 'none');
  });
  root.querySelectorAll('*').forEach((el) => {
    Array.from(el.attributes).forEach((attr) => {
      const name = attr.name.toLowerCase();
      if (name.startsWith('on')) { el.removeAttribute(attr.name); return; }
      if (name === 'href' || name === 'xlink:href') {
        const value = (attr.value || '').trim();
        if (!/^(https?:\/\/|mailto:|#)/i.test(value)) {
          el.removeAttribute(attr.name);
        }
      }
    });
  });
}

function renderMarkdown(text) {
  const html = marked.parse(text == null ? '' : String(text));
  const doc = new DOMParser().parseFromString(html, 'text/html');
  sanitizeMarkdownNode(doc.body);
  return doc.body.innerHTML;
}

// Initialize mermaid
async function initMermaid() {
  if (typeof mermaid !== 'undefined') {
    mermaidModule = mermaid;
    mermaidModule.initialize({
      theme: 'dark',
      startOnLoad: false,
      // 'strict', not 'loose': a mermaid fence is model-authored text and
      // its rendered SVG goes into innerHTML below. Under 'loose' a
      // `click A href "javascript:..."` directive survives into a live
      // <a xlink:href>, and clicking the diagram node executes it in the
      // UI's origin - verified end to end 2026-08-29. 'strict' strips
      // javascript: from click directives; the SVG is walked as well, so
      // the boundary does not rest on mermaid alone.
      securityLevel: 'strict',
    });
  }
}

// DOM Elements
let statusDot, statusText, messagesContainer, textInput, sendBtn;
let fileList, searchInput, searchResults, reindexBtn, modelSelect;
let sidebar, sidebarToggle, mainLayout, folderTree, recentFilesList;

// Recent files tracking
const MAX_RECENT_FILES = 5;
let recentFiles = JSON.parse(localStorage.getItem('brain_recent_files') || '[]');

async function init() {
  // Get DOM elements
  statusDot = document.getElementById('status-dot');
  statusText = document.getElementById('status-text');
  messagesContainer = document.getElementById('messages');
  textInput = document.getElementById('text-input');
  sendBtn = document.getElementById('send-btn');
  fileList = document.getElementById('file-list');
  searchInput = document.getElementById('search-input');
  searchResults = document.getElementById('search-results');
  reindexBtn = document.getElementById('reindex-btn');
  modelSelect = document.getElementById('model-select');
  sidebar = document.getElementById('sidebar');
  sidebarToggle = document.getElementById('sidebar-toggle');
  mainLayout = document.getElementById('main-layout');
  folderTree = document.getElementById('folder-tree');
  recentFilesList = document.getElementById('recent-files-list');

  // Restore sidebar and rail state
  const sidebarCollapsed = localStorage.getItem('sidebar_collapsed') === 'true';
  if (sidebarCollapsed && sidebar && mainLayout) {
    sidebar.classList.add('collapsed');
    mainLayout.classList.add('sidebar-collapsed');
  }
  if (localStorage.getItem('rail_open') === '1') setRailOpen(true);

  // Restore collapsible section states. Conversations and Recent open by
  // default; every other section starts closed until the user opens it.
  const OPEN_BY_DEFAULT = ['conversations', 'recent'];
  document.querySelectorAll('.sidebar-section.collapsible').forEach(section => {
    const stored = localStorage.getItem('sidebar_section_' + section.dataset.section);
    const collapsed = stored === null
      ? !OPEN_BY_DEFAULT.includes(section.dataset.section)
      : stored === 'true';
    if (collapsed) section.classList.add('collapsed');
  });

  // Initialize markdown + mermaid
  initMarkdown();
  await initMermaid();

  // Load conversations and open the most recently UPDATED thread - the
  // list is newest-first, so boot always lands on the latest activity
  // (conversations created outside this browser included) rather than a
  // stale localStorage pin from an old session.
  await loadConversations();
  if (conversations.length > 0) {
    await switchConversation(conversations[0].id);
  } else {
    await createNewConversation();
  }

  // Load initial data
  loadToken();
  loadModels();
  loadClaudeSettings();
  loadSeatRoster();
  loadSeats();
  setupEventListeners();
  loadFileList();
  loadIndexStats();
  renderRecentFiles();
}

document.addEventListener('DOMContentLoaded', init);

// Conversation Management
async function createNewConversation() {
  try {
    const resp = await fetch(`${API_BASE}/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const data = await resp.json();
    currentConversationId = data.id;
    localStorage.setItem('brain_current_conversation', currentConversationId);
    clearMessages();
    // Refresh list
    await loadConversations();
    renderConversationList();
    return data.id;
  } catch (err) {
    console.error('Failed to create conversation:', err);
  }
}

async function loadConversations() {
  try {
    const limit = conversationListExpanded ? 0 : CONVERSATION_PAGE_SIZE;
    const url = limit
      ? `${API_BASE}/conversations?limit=${limit}`
      : `${API_BASE}/conversations`;
    const resp = await fetch(url);
    const totalHeader = resp.headers.get('X-Total-Count');
    conversationTotalCount = totalHeader ? parseInt(totalHeader, 10) : 0;
    conversations = await resp.json();
    renderConversationList();
  } catch (err) {
    console.error('Failed to load conversations:', err);
    conversations = [];
    conversationTotalCount = 0;
  }
}

async function switchConversation(id) {
  currentConversationId = id;
  localStorage.setItem('brain_current_conversation', id);
  await loadConversationMessages(id);
  renderConversationList();
  loadSeats();
  // Reflect this thread's model pin in the picker (falls back to the
  // process-wide current from /models when the thread has none).
  try {
    const thread = await (await fetch(`${API_BASE}/conversations/${id}`)).json();
    if (thread.model && modelSelect) modelSelect.value = thread.model;
    else loadModels();
  } catch (err) { /* picker keeps its current value */ }
}

async function deleteConversation(id) {
  try {
    await fetch(`${API_BASE}/conversations/${id}`, { method: 'DELETE' });
  } catch (err) {
    console.error('Failed to delete conversation:', err);
  }
  conversations = conversations.filter(c => c.id !== id);
  if (currentConversationId === id) {
    if (conversations.length > 0) {
      await switchConversation(conversations[0].id);
    } else {
      await createNewConversation();
    }
  } else {
    renderConversationList();
  }
}

async function loadConversationMessages(conversationId) {
  try {
    const resp = await fetch(`${API_BASE}/conversations/${conversationId}`);
    const data = await resp.json();
    clearMessages();
    const seatNames = {};
    for (const s of data.participants || []) seatNames[s.id] = s.name;
    for (const turn of data.turns) {
      // a pass is a yielded turn, not content: it renders as nothing
      if (turn.passed) continue;
      if (turn.role === 'user') {
        appendUserMessage(turn.content);
      } else if (turn.role === 'assistant') {
        appendAgentMessage(turn.content, turn.speaker,
                           seatNames[turn.speaker]);
      }
    }
    scrollToBottom();
  } catch (err) {
    console.error('Failed to load conversation:', err);
    clearMessages();
  }
}

function renderConversationList() {
  const listEl = document.getElementById('conversation-list');
  if (!listEl) return;
  const items = conversations.map(c => `
    <li class="conversation-item ${c.id === currentConversationId ? 'active' : ''}"
        data-action="switch-conversation" data-id="${escapeHtml(c.id)}">
      <span class="conversation-title">${escapeHtml(c.title || 'New Chat')}</span>
      <button class="conversation-delete" data-action="delete-conversation"
              data-id="${escapeHtml(c.id)}" title="Delete">&times;</button>
    </li>
  `).join('');
  let footer = '';
  const showingTruncated =
    !conversationListExpanded &&
    conversationTotalCount > conversations.length;
  if (showingTruncated) {
    const more = conversationTotalCount - conversations.length;
    footer = `
      <li class="conversation-item conversation-show-more"
          data-action="toggle-conversation-list">
        <span class="conversation-title">Show ${more} more...</span>
      </li>`;
  } else if (conversationListExpanded && conversationTotalCount > CONVERSATION_PAGE_SIZE) {
    footer = `
      <li class="conversation-item conversation-show-more"
          data-action="toggle-conversation-list">
        <span class="conversation-title">Show fewer</span>
      </li>`;
  }
  listEl.innerHTML = items + footer;
}

async function toggleConversationListExpanded() {
  conversationListExpanded = !conversationListExpanded;
  await loadConversations();
}
function clearMessages() {
  if (messagesContainer) {
    messagesContainer.innerHTML = '';
  }
}

// Token Management
function loadToken() {
  let token = localStorage.getItem('brain_token');
  if (!token) {
    token = 'brain_' + Math.random().toString(36).substring(2, 15);
    localStorage.setItem('brain_token', token);
  }
  connect(token);
}

function saveToken(token) {
  localStorage.setItem('brain_token', token);
}

// Model Management
// Model tier + effort for launched claude agents (main and seats):
// reads/writes ~/.brain/config through /settings/claude; lanes read
// config at call time, so a change applies from the next turn.
async function loadClaudeSettings() {
  const modelEl = document.getElementById('claude-model-select');
  const effortEl = document.getElementById('claude-effort-select');
  if (!modelEl || !effortEl) return;
  try {
    const body = await (await fetch(`${API_BASE}/settings/claude`)).json();
    if (body.model && ![...modelEl.options].some(o => o.value === body.model)) {
      modelEl.add(new Option(body.model, body.model));
    }
    if (body.model) modelEl.value = body.model;
    if (body.effort) effortEl.value = body.effort;
  } catch (err) { console.error('Failed to load claude settings:', err); }
}

async function saveClaudeSettings() {
  const modelEl = document.getElementById('claude-model-select');
  const effortEl = document.getElementById('claude-effort-select');
  try {
    await fetch(`${API_BASE}/settings/claude`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: modelEl.value, effort: effortEl.value }),
    });
  } catch (err) { console.error('Failed to save claude settings:', err); }
}

async function loadModels() {
  try {
    const resp = await fetch(`${API_BASE}/models`);
    const data = await resp.json();
    const { models, current } = data;
    // Populate datalist with available models
    const datalist = document.getElementById('model-list');
    if (datalist) {
      datalist.innerHTML = models.map(m =>
        `<option value="${m}">`
      ).join('');
    }
    // Set current model in the input
    if (modelSelect) {
      modelSelect.value = current || '';
    }
  } catch (err) {
    console.error('Failed to load models:', err);
    if (modelSelect) modelSelect.placeholder = 'Error loading models';
  }
}

// --- Group-chat seats (SPEC-GROUP-CHAT-V1 G1) ---

async function loadSeats() {
  const listEl = document.getElementById('seat-list');
  if (!listEl || !currentConversationId) return;
  try {
    const thread = await (await fetch(`${API_BASE}/conversations/${currentConversationId}`)).json();
    const seats = thread.participants || [];
    listEl.innerHTML = seats.length === 0
      ? '<div class="seat-empty">No seats - two-party chat</div>'
      : seats.map(s => `
        <div class="seat-row ${seatAccent(s.id)}" data-seat="${escapeHtml(s.id)}">
          <span class="seat-row-name">${escapeHtml(s.name)}</span>
          <span class="seat-row-cwd" title="${escapeHtml(s.cwd)}">${escapeHtml(s.cwd)}</span>
          <span class="seat-row-policy" title="Effective policy"
                data-action="seat-policy" data-id="${escapeHtml(s.id)}">policy</span>
          <span class="seat-row-remove" title="Remove seat"
                data-action="remove-seat" data-id="${escapeHtml(s.id)}">&times;</span>
        </div>`).join('');
  } catch (err) { console.error('Failed to load seats:', err); }
}

// The effective-policy card: what the spawner will pass and what the
// harness will read, attributed to its source. Display only - no control
// here writes a grant; a headless turn could not consume one anyway.
async function toggleSeatPolicy(id) {
  const row = document.querySelector(`.seat-row[data-seat="${CSS.escape(id)}"]`);
  if (!row || !currentConversationId) return;
  const open = row.nextElementSibling;
  if (open && open.classList.contains('seat-policy')) { open.remove(); return; }
  let p;
  try {
    const resp = await fetch(`${API_BASE}/conversations/${currentConversationId}/participants/${encodeURIComponent(id)}/policy`);
    if (!resp.ok) return;
    p = await resp.json();
  } catch (err) { return; }
  const src = (t) => `<span class="policy-source">${escapeHtml(t)}</span>`;
  const rules = (list) => list.length
    ? list.map(r => `<li><code>${escapeHtml(r.rule)}</code> ${src(r.source)}</li>`).join('')
    : '<li class="policy-none">none</li>';
  const pick = (v) => `${escapeHtml(v.resolved || 'default')} ${src(v.source +
    (v.declared && v.declared !== v.resolved ? ` · roster says ${v.declared}` : ''))}`;
  const card = document.createElement('div');
  card.className = 'seat-policy';
  card.innerHTML = `
    <div class="policy-head">effective policy · display only</div>
    <dl>
      <dt>model</dt><dd>${pick(p.model)}</dd>
      <dt>effort</dt><dd>${pick(p.effort)}</dd>
      <dt>cwd</dt><dd>${escapeHtml(p.cwd)} ${src(p.trusted ? 'trusted' : 'untrusted: committed allows ignored')}${p.readonly ? ' ' + src('read-only seat') : ''}</dd>
      <dt>gate</dt><dd>memory pressure level ${escapeHtml(String(p.gate.level ?? 'unknown'))}${p.gate.ack_fresh ? ' · ack fresh' : ''}</dd>
    </dl>
    <div class="policy-title">allows</div><ul>${rules(p.allow)}</ul>
    <div class="policy-title">denies</div><ul>${rules(p.deny)}</ul>
    <div class="policy-title">hooks</div><ul>${p.hooks.length ? p.hooks.map(h =>
      `<li><code>${escapeHtml(h.event)}</code> ${escapeHtml(h.matcher || '*')} · ${escapeHtml(h.command)} ${src(h.source + (h.headless ? ' · ' + h.headless : ''))}</li>`).join('')
      : '<li class="policy-none">none</li>'}</ul>`;
  row.insertAdjacentElement('afterend', card);
}

async function loadSeatRoster() {
  const datalist = document.getElementById('seat-roster');
  if (!datalist) return;
  try {
    const body = await (await fetch(`${API_BASE}/seats`)).json();
    datalist.innerHTML = (body.seats || []).map(s =>
      `<option value="${escapeHtml(s.name)}" label="${escapeHtml(s.cwd)}">`).join('');
    window._seatRoster = body.seats || [];
  } catch (err) { window._seatRoster = []; }
}

async function addSeat() {
  const nameEl = document.getElementById('seat-name');
  const cwdEl = document.getElementById('seat-cwd');
  const name = (nameEl.value || '').trim();
  if (!name) return;
  if (!currentConversationId) await createNewConversation();
  // A roster pick fills cwd/harness/model when the field is left blank.
  const roster = (window._seatRoster || []).find(s => s.name === name);
  const body = {
    name,
    cwd: (cwdEl.value || '').trim() || (roster ? roster.cwd : ''),
    harness: roster ? (roster.harness || 'claude') : 'claude',
    model: roster ? (roster.model || '') : '',
  };
  try {
    const resp = await fetch(`${API_BASE}/conversations/${currentConversationId}/participants`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (resp.ok) { nameEl.value = ''; cwdEl.value = ''; loadSeats(); }
  } catch (err) { console.error('Failed to add seat:', err); }
}
function setRoundCancelVisible(on) {
  const btn = document.getElementById('round-cancel-btn');
  if (btn) btn.classList.toggle('hidden', !on);
}

// Composer busy state: the input always accepts queued messages, but the
// placeholder and send button say whose turn it is, and Esc interrupts
// the running turn (the server kills the active subprocess mid-stream).
let activeStreams = 0;
function setComposerBusy(busy) {
  activeStreams = Math.max(0, activeStreams + (busy ? 1 : -1));
  const nowBusy = activeStreams > 0;
  if (textInput) {
    textInput.placeholder = nowBusy
      ? 'Agents are speaking - Enter queues your message, Esc interrupts'
      : 'Message your second brain...';
  }
  if (sendBtn) {
    sendBtn.classList.toggle('busy', nowBusy);
    if (!nowBusy) {
      sendBtn.classList.add('ready-pulse');
      setTimeout(() => sendBtn.classList.remove('ready-pulse'), 1300);
    }
  }
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && activeStreams > 0 && currentConversationId) {
    cancelRound();
    showActivity('Interrupting - the current turn ends shortly');
  }
});

function cancelRound() {
  if (!currentConversationId) return;
  fetch(`${API_BASE}/conversations/${currentConversationId}/cancel`,
        { method: 'POST' }).catch(() => {});
}
async function removeSeat(seatId) {
  try {
    await fetch(`${API_BASE}/conversations/${currentConversationId}/participants/${seatId}`, { method: 'DELETE' });
  } catch (err) {}
  loadSeats();
}
function switchModel(model) {
  // With a conversation open, the pin sticks to that thread; otherwise
  // it sets the process-wide default (per-conversation model, R29).
  const body = { model };
  if (currentConversationId) body.conversation_id = currentConversationId;
  fetch(`${API_BASE}/model`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).catch(err => console.error('Failed to switch model:', err));
}

// SSE Connection
function connect(token) {
  if (eventSource) {
    eventSource.close();
  }

  eventSource = new EventSource(`${API_BASE}/sse?token=${token}`);

  eventSource.onopen = () => {
    console.log('SSE connected');
    statusDot.className = 'dot dot-connected';
    statusText.textContent = 'Connected';
    if (document.getElementById('input-bar')) {
      document.getElementById('input-bar').classList.remove('hidden');
    }
  };

  eventSource.onerror = (err) => {
    console.log('SSE error:', err);
    statusDot.className = 'dot dot-disconnected';
    statusText.textContent = 'Disconnected';
    if (document.getElementById('input-bar')) {
      document.getElementById('input-bar').classList.add('hidden');
    }
  };

  eventSource.addEventListener('message', handleSSEMessage);
}

function handleSSEMessage(event) {
  const data = JSON.parse(event.data);
  if (data.type === 'chunk') {
    appendAgentChunk(data.content);
  } else if (data.type === 'done') {
    finalizeAgentMessage();
  } else if (data.type === 'file_created' || data.type === 'file_updated') {
    loadFileList();
    loadIndexStats();
  }
}

// Chat with streaming
async function sendMessage() {
  const content = textInput.value.trim();
  if (!content) return;

  // Auto-create conversation if none exists
  if (!currentConversationId) {
    await createNewConversation();
    if (!currentConversationId) return;
  }

  appendUserMessage(content);
  textInput.value = '';
  textInput.style.height = 'auto';
  showActivity('Searching knowledge base...');
  setComposerBusy(true);

  fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: content, conversation_id: currentConversationId }),
  })
  .then(r => {
    if (!r.ok) throw new Error('Network error');
    return r;
  })
  .then(response => {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentMsg = null;
    let currentSpeaker = null;

    // parseSse is the shared frame parser from kb-graph-hud.js: it retains a
    // partial trailing line across chunk reads and joins multi-line data:
    // fields, which the old hand-rolled reader got wrong.
    function dispatchEvent(ev) {
      // token_usage frames still stream (and persist server-side) but the
      // UI meter is gone - per-session figures in a group thread made the
      // displayed number misleading.
      if (ev.type === 'token_usage') return;
      // Group-chat frames (SPEC-GROUP-CHAT-V1 G5): dividers and
      // per-speaker bubbles keyed off iteration_start attribution.
      if (ev.type === 'round_start') {
        appendRoundDivider(ev.data);
        setRoundCancelVisible(true);
        return;
      }
      if (ev.type === 'done') {
        setRoundCancelVisible(false);
        clearPrepIndicators();
        // Finalize directly - routing done through handleStreamEvent would
        // conjure an empty bubble when the round's last bubble was a
        // dropped pass (currentMsg reset above).
        finalizeAgentMessage();
        return;
      }
      if (ev.type === 'seat_done') {
        // A dropped pass bubble must stop being currentMsg, or the same
        // seat's next turn (same speaker, no bubble switch) would stream
        // into a detached node and render nowhere.
        if (handleSeatDone(ev.data)) {
          currentMsg = null;
          currentSpeaker = null;
        }
        return;
      }
      if (ev.type === 'round_done') {
        // a round nobody spoke in now renders nothing, so its divider goes too
        try {
          if (!(JSON.parse(ev.data).spoke || []).length) {
            const last = messagesContainer.lastElementChild;
            if (last && last.classList.contains('round-divider')) last.remove();
          }
        } catch (e) {}
        return;
      }
      // G10 prep frames: a seat researching in parallel - never rendered
      // in the transcript; the seats panel shows the activity instead.
      if (ev.type !== 'done' && ev.type !== 'kb_file') {
        try {
          const p = JSON.parse(ev.data);
          if (p && p.prep) { notePrepActivity(p); return; }
        } catch (e) {}
      }
      if (ev.type === 'iteration_start') {
        try {
          const info = JSON.parse(ev.data);
          if (info.speaker) clearPrepIndicators(info.speaker);
          if (info.speaker && info.speaker !== currentSpeaker) {
            finalizeAgentMessage();
            currentMsg = createAgentMessage(info.speaker, info.speaker_name);
            currentSpeaker = info.speaker;
          }
        } catch (e) {}
      }
      handleStreamEvent(ev.type, ev.data, () => {
        if (!currentMsg) currentMsg = createAgentMessage();
        return currentMsg;
      });
    }

    function readStream() {
      reader.read().then(({ done, value }) => {
        if (done) {
          finalizeAgentMessage();
          hideActivity();
          setComposerBusy(false);
          // Refresh conversation list (title may have updated)
          loadConversations();
          return;
        }
        const parsed = window.parseSse(buffer, decoder.decode(value, { stream: true }));
        buffer = parsed.buffer;
        parsed.events.forEach(dispatchEvent);
        readStream();
      });
    }
    readStream();
  })
  .catch(err => {
    console.error('Chat error:', err);
    hideActivity();
    setComposerBusy(false);
    appendAgentMessage('Error: Connection lost');
  });
}

// --- Phase 2: per-iteration message DOM ---
//
// Each tool-loop iteration gets its own .iteration block with three slots:
//   .iteration-thinking : reasoning tokens
//   .iteration-tools    : tool-call bubbles (PERSISTENT, never re-rendered)
//   .iteration-text     : streamed markdown (re-rendered every 150ms)
//
// Re-renders only target .iteration-text so tool bubbles never get wiped.

const BRACKETED_TOOL_RE = /\[TOOL:\s*[a-zA-Z_][a-zA-Z0-9_]*(?:\([^)]*\))?\s*\]/g;

function stripToolMarkers(text) {
  if (!text) return text;
  return text.replace(BRACKETED_TOOL_RE, '');
}

function ensureIteration(msg, iterationIndex) {
  const contentEl = msg.querySelector('.message-content');
  let iter = contentEl.querySelector(`.iteration[data-i="${iterationIndex}"]`);
  if (!iter) {
    iter = document.createElement('div');
    iter.className = 'iteration';
    iter.dataset.i = String(iterationIndex);
    iter.innerHTML = `
      <div class="iteration-thinking"></div>
      <div class="iteration-tools"></div>
      <div class="iteration-text"></div>
    `;
    contentEl.appendChild(iter);
  }
  return iter;
}

function getCurrentIteration(msg) {
  const contentEl = msg.querySelector('.message-content');
  // Default to iteration 0 if server didn't emit iteration_start (back-compat)
  const all = contentEl.querySelectorAll('.iteration');
  if (all.length === 0) return ensureIteration(msg, 0);
  return all[all.length - 1];
}

function setStreamingCursor(msg, on) {
  let cursor = msg.querySelector('.streaming-cursor');
  if (on) {
    if (!cursor) {
      cursor = document.createElement('span');
      cursor.className = 'streaming-cursor';
      cursor.textContent = '▌';
      msg.querySelector('.message-content').appendChild(cursor);
    }
  } else if (cursor) {
    cursor.remove();
  }
}

function setActivityPulse(msg, label) {
  let pulse = msg.querySelector('.activity-pulse');
  if (label) {
    if (!pulse) {
      pulse = document.createElement('div');
      pulse.className = 'activity-pulse';
      pulse.innerHTML = `<span class="activity-pulse-dots"><span></span><span></span><span></span></span> <span class="activity-pulse-label"></span>`;
      msg.querySelector('.message-content').appendChild(pulse);
    }
    pulse.querySelector('.activity-pulse-label').textContent = label;
  } else if (pulse) {
    pulse.remove();
  }
}

function noteActivity(msg) {
  msg._lastTokenAt = Date.now();
  setActivityPulse(msg, null);
  if (msg._idleWatcher) {
    clearTimeout(msg._idleWatcher);
  }
  msg._idleWatcher = setTimeout(() => {
    if (Date.now() - (msg._lastTokenAt || 0) >= 2000 && msg.classList.contains('streaming')) {
      setActivityPulse(msg, 'Thinking…');
    }
  }, 2200);
}

function startToolTimer(bubble) {
  if (bubble._timerInterval) {
    clearInterval(bubble._timerInterval);
    bubble._timerInterval = null;
  }
  const startedAt = Date.now();
  bubble._timerInterval = setInterval(() => {
    const elapsed = Math.round((Date.now() - startedAt) / 1000);
    const elapsedEl = bubble.querySelector('.tool-bubble-elapsed');
    if (elapsedEl) elapsedEl.textContent = `${elapsed}s`;
  }, 500);
}

function stopToolTimer(bubble, elapsedMs) {
  if (bubble._timerInterval) {
    clearInterval(bubble._timerInterval);
    bubble._timerInterval = null;
  }
  const elapsedEl = bubble.querySelector('.tool-bubble-elapsed');
  if (elapsedEl) {
    if (typeof elapsedMs === 'number') {
      const secs = (elapsedMs / 1000).toFixed(elapsedMs < 1000 ? 2 : 1);
      elapsedEl.textContent = `${secs}s`;
    }
  }
}

// --- Activity rail -------------------------------------------------------
//
// Tool calls and thinking never render inside a reply. Each streaming
// message gets one section in #rail-feed, colored by its seat, and the
// reply carries a footer that jumps to that section; the section header
// jumps back. Sessions only: reloaded threads have no feed (user
// decision 2026-09-02), so the link keys on a per-session turn counter.

let turnCounter = 0;
let railTouched = false;   // toggled by hand this session: no auto-open

function setRailOpen(open) {
  mainLayout.classList.toggle('rail-open', open);
  const btn = document.getElementById('rail-toggle');
  if (btn) btn.classList.toggle('active', open);
  localStorage.setItem('rail_open', open ? '1' : '0');
}

function toggleRail() {
  railTouched = true;
  setRailOpen(!mainLayout.classList.contains('rail-open'));
}

// The first tool call of a session opens the rail once, so the activity
// is never invisible by default; a user who closed it stays in charge.
function railAutoOpen() {
  if (railTouched || localStorage.getItem('rail_open') === '0') return;
  if (!mainLayout.classList.contains('rail-open')) setRailOpen(true);
}

function feedSection(msg) {
  if (msg._feed) return msg._feed;
  const feed = document.getElementById('rail-feed');
  const empty = feed.querySelector('.rail-empty');
  if (empty) empty.remove();
  const turn = msg.dataset.turn;
  const speaker = msg.dataset.speaker || '';
  const chip = msg.querySelector('.speaker-chip');
  const section = document.createElement('section');
  section.className = 'feed-turn' + (speaker ? ' ' + seatAccent(speaker) : '');
  section.dataset.turn = turn;
  section.innerHTML = `
    <div class="feed-turn-header" data-action="jump-to-turn" data-turn="${escapeHtml(turn)}">
      <span class="feed-turn-speaker">${escapeHtml(chip ? chip.textContent : 'B')}</span>
      <span class="feed-turn-count"></span>
    </div>
    <div class="feed-rows"></div>`;
  feed.appendChild(section);
  msg._feed = section;
  turnFooter(msg);
  railAutoOpen();
  return section;
}

function turnFooter(msg) {
  let footer = msg.querySelector('.turn-footer');
  if (!footer) {
    msg.insertAdjacentHTML('beforeend',
      `<button class="turn-footer" data-action="jump-to-feed" data-turn="${escapeHtml(msg.dataset.turn)}">thinking</button>`);
    footer = msg.querySelector('.turn-footer');
  }
  return footer;
}

function updateTurnCounts(msg) {
  const section = msg._feed;
  if (!section) return;
  const n = section.querySelectorAll('.tool-call-bubble').length;
  const running = section.querySelectorAll('.tool-call-bubble.running').length;
  const denied = section.querySelectorAll('.tool-call-bubble.denied').length;
  let label = n === 0 ? 'thinking' : `${n} tool call${n === 1 ? '' : 's'}`;
  if (running) label += ` · ${running} running`;
  if (denied) label += ` · ${denied} denied`;
  turnFooter(msg).textContent = label;
  section.querySelector('.feed-turn-count').textContent = n ? String(n) : '';
}

let _feedFollowQueued = false;
function feedFollow() {
  if (_feedFollowQueued) return;
  _feedFollowQueued = true;
  requestAnimationFrame(() => {
    _feedFollowQueued = false;
    const feed = document.getElementById('rail-feed');
    if (feed) feed.scrollTop = feed.scrollHeight;
  });
}

function flash(el) {
  el.classList.remove('flash');
  requestAnimationFrame(() => el.classList.add('flash'));
}

function jumpToFeed(turn) {
  if (!mainLayout.classList.contains('rail-open')) { railTouched = true; setRailOpen(true); }
  const section = document.querySelector(`.feed-turn[data-turn="${CSS.escape(turn)}"]`);
  if (!section) return;
  section.scrollIntoView({ block: 'start', behavior: 'smooth' });
  flash(section);
}

function jumpToTurn(turn) {
  const msg = messagesContainer.querySelector(`.message[data-turn="${CSS.escape(turn)}"]`);
  if (!msg) return;
  msg.scrollIntoView({ block: 'center', behavior: 'smooth' });
  flash(msg);
}

// One line per call: the tool, the one argument a reader scans for, the
// time. Everything else waits in the body for a click.
const SUMMARY_PATH_KEYS = ['filename', 'file_path', 'path', 'file', 'folder', 'notebook_path'];
const SUMMARY_TEXT_KEYS = ['command', 'pattern', 'query', 'q', 'url', 'prompt', 'description'];

function shortPath(p) {
  const parts = p.split('/').filter(Boolean);
  return parts.length > 3 ? '…/' + parts.slice(-3).join('/') : p;
}

function toolSummary(args) {
  if (!args || typeof args !== 'object') return '';
  for (const k of SUMMARY_TEXT_KEYS) {
    if (typeof args[k] === 'string' && args[k]) return args[k].replace(/\s+/g, ' ').slice(0, 160);
  }
  for (const k of SUMMARY_PATH_KEYS) {
    if (typeof args[k] === 'string' && args[k]) return shortPath(args[k]);
  }
  const first = Object.values(args).find(v => typeof v === 'string' && v);
  return first ? first.replace(/\s+/g, ' ').slice(0, 160) : '';
}

function toolRow(toolInfo) {
  const row = document.createElement('div');
  // born collapsed: the body holds the full arguments now and the result
  // once it lands (rendered on first expand)
  row.className = 'tool-call-bubble running collapsed';
  row.dataset.tool = toolInfo.tool;
  row.innerHTML = `
    <div class="tool-bubble-header" data-action="toggle-bubble">
      <svg class="tool-bubble-toggle" viewBox="0 0 16 16" fill="currentColor">
        <path d="M8 11L3 6h10l-5 5z"/>
      </svg>
      <span class="tool-bubble-title"><span class="row-tool">${escapeHtml(toolInfo.tool)}</span><span class="row-arg">${escapeHtml(toolSummary(toolInfo.args))}</span></span>
      <span class="tool-bubble-elapsed">0s</span>
    </div>
    <div class="tool-bubble-content"><div class="row-args">${formatToolArgsForDisplay(toolInfo.tool, toolInfo.args)}</div></div>
  `;
  return row;
}

/** A refused call: tool, source, rule, and the reason text as plain text. */
function deniedRow(info) {
  const row = document.createElement('div');
  row.className = 'tool-call-bubble denied';
  row.dataset.tool = info.tool;
  const rule = info.rule ? ` · ${escapeHtml(info.rule)}` : '';
  row.innerHTML = `
    <div class="tool-bubble-header">
      <span class="tool-bubble-title"><span class="denied-badge">denied</span><span class="row-tool">${escapeHtml(info.tool)}</span><span class="row-arg">${escapeHtml(info.source)}${rule}</span></span>
    </div>` + (info.reason ? `<div class="denied-reason">${escapeHtml(info.reason)}</div>` : '');
  return row;
}

/** Last running row for this tool in the section (tool_done matches the same). */
function findLastRunningToolBubble(iter, toolName) {
  const all = iter.querySelectorAll('.tool-call-bubble');
  let found = null;
  for (const b of all) {
    if (b.dataset.tool === toolName && b.classList.contains('running')) {
      found = b;
    }
  }
  return found;
}

/**
 * Compact tool args for the bubble header - never dump full save_knowledge body.
 */
function formatToolArgsForDisplay(tool, args) {
  if (!args || typeof args !== 'object') {
    return '';
  }
  const MAX_INLINE = 380;
  const parts = [];
  for (const [k, v] of Object.entries(args)) {
    let s = v === null || v === undefined ? '' : String(v);
    if (tool === 'save_knowledge' && k === 'content') {
      const n = s.length;
      if (n <= 200) {
        parts.push(`content: "${escapeHtml(s)}"`);
      } else {
        const preview = s.slice(0, 120).replace(/\s+/g, ' ').trim();
        parts.push(`content: <${n.toLocaleString()} chars> "${escapeHtml(preview)}…"`);
      }
      continue;
    }
    if (s.length > MAX_INLINE) {
      const preview = escapeHtml(s.slice(0, 120).replace(/\n/g, ' '));
      parts.push(`${k}: <${s.length.toLocaleString()} chars> "${preview}…"`);
    } else {
      parts.push(`${k}: ${escapeHtml(s)}`);
    }
  }
  return parts.join(', ');
}

function handleStreamEvent(type, data, getMsg) {
  const msg = getMsg();

  switch (type) {
    case 'kb_context':
      showActivity(`Found ${data} in knowledge base`);
      break;
    case 'kb_file':
      try {
        const file = JSON.parse(data);
        appendKBResult(file.path, file.score);
      } catch (e) {}
      break;

    case 'iteration_start': {
      let iterIdx = 0;
      try {
        const info = JSON.parse(data);
        iterIdx = info.iteration ?? 0;
      } catch (e) {}
      ensureIteration(msg, iterIdx);
      noteActivity(msg);
      break;
    }

    case 'thinking': {
      const decoded = decodeURIComponent(data);
      const section = feedSection(msg);
      let row = section._thinking;
      if (!row) {
        row = document.createElement('div');
        // born collapsed: reasoning is a peek, not a wall (expand on click)
        row.className = 'thinking-bubble collapsed';
        row.innerHTML = `
          <div class="thinking-bubble-header" data-action="toggle-bubble">
            <span class="thinking-bubble-title">
              <svg class="thinking-bubble-toggle" viewBox="0 0 16 16" fill="currentColor">
                <path d="M8 11L3 6h10l-5 5z"/>
              </svg>
              Thinking
            </span>
          </div>
          <div class="thinking-bubble-content"></div>
        `;
        section.querySelector('.feed-rows').appendChild(row);
        section._thinking = row;
        feedFollow();
      }
      // deltas batch per frame: one text write, not one per token
      row._buf = (row._buf || '') + decoded;
      if (!row._flush) {
        row._flush = requestAnimationFrame(() => {
          row._flush = 0;
          row.querySelector('.thinking-bubble-content').textContent = row._buf;
        });
      }
      noteActivity(msg);
      break;
    }

    case 'token': {
      const decodedToken = decodeURIComponent(data);
      const iter = getCurrentIteration(msg);
      const textEl = iter.querySelector('.iteration-text');
      // Strip raw [TOOL: ...] / bare tool_name(args) from the visible stream;
      // server-side parsing still acts on them via the tool_call SSE event.
      const cleaned = stripToolMarkers(decodedToken);
      textEl._rawText = (textEl._rawText || '') + cleaned;
      if (!textEl._renderTimer) {
        textEl._renderTimer = setTimeout(() => {
          // IMPORTANT: re-render targets only the text slot, not the whole
          // message-content. Tool bubbles in .iteration-tools survive.
          const fullClean = stripToolMarkers(textEl._rawText);
          textEl.innerHTML = renderMarkdown(fullClean);
          textEl._renderTimer = null;
          setStreamingCursor(msg, true);
          scrollToBottom();
        }, 150);
      }
      noteActivity(msg);
      break;
    }

    case 'error': {
      const iter = getCurrentIteration(msg);
      const textEl = iter.querySelector('.iteration-text');
      textEl._rawText = (textEl._rawText || '') + `\n[Error: ${data}]`;
      textEl.innerHTML = renderMarkdown(textEl._rawText);
      break;
    }

    case 'tool_call':
    case 'tool_executing': {
      try {
        const toolInfo = JSON.parse(data);
        const section = feedSection(msg);
        let row = type === 'tool_executing'
          ? findLastRunningToolBubble(section, toolInfo.tool) : null;
        if (!row) {
          row = toolRow(toolInfo);
          section.querySelector('.feed-rows').appendChild(row);
        }
        startToolTimer(row);
        updateTurnCounts(msg);
        showActivity(`${toolInfo.tool} running`);
        noteActivity(msg);
        feedFollow();
      } catch (e) {}
      break;
    }

    case 'tool_done': {
      try {
        const info = JSON.parse(data);
        const section = feedSection(msg);
        const rows = section.querySelectorAll(`.tool-call-bubble[data-tool="${info.tool}"].running`);
        const row = rows[rows.length - 1];
        if (row) {
          stopToolTimer(row, info.elapsed_ms);
          row.classList.remove('running');
        }
        updateTurnCounts(msg);
      } catch (e) {}
      break;
    }

    case 'guardrails': {
      try {
        const info = JSON.parse(data);
        const section = feedSection(msg);
        const row = document.createElement('div');
        row.className = 'tool-call-bubble guardrails';
        row.innerHTML = `<div class="tool-bubble-header"><span class="tool-bubble-title"><span class="denied-badge">guardrails changed</span><span class="row-arg">${escapeHtml(info.seat)} starts a fresh session under the current hooks and rules</span></span></div>`;
        section.querySelector('.feed-rows').appendChild(row);
        noteActivity(msg);
        feedFollow();
      } catch (e) {}
      break;
    }

    case 'denied': {
      // A refused call, attributed by the server to its source. Display
      // only: no approve button exists, a headless turn could not use one.
      try {
        const info = JSON.parse(data);
        const section = feedSection(msg);
        section.querySelector('.feed-rows').appendChild(deniedRow(info));
        updateTurnCounts(msg);
        noteActivity(msg);
        feedFollow();
      } catch (e) {}
      break;
    }

    case 'tool_result': {
      try {
        const resultInfo = JSON.parse(data);
        const section = feedSection(msg);
        // Match the most recent row for this tool (running or just-stopped)
        const matching = section.querySelectorAll(`.tool-call-bubble[data-tool="${resultInfo.tool}"]`);
        const row = matching[matching.length - 1] ||
                    section.querySelector('.tool-call-bubble:last-of-type');
        if (row) {
          stopToolTimer(row);
          row.classList.remove('running');
          if (resultInfo.executed === false) row.classList.add('tool-not-executed');
          // Phase 1 servers emit { result, info }; older servers emit { result_preview }.
          // Kept as text and rendered on first expand (toggle-bubble).
          const fullResult = resultInfo.result || resultInfo.result_preview || '';
          row._result = fullResult;
          if (resultInfo.info && fullResult.length > 2000) {
            const meta = document.createElement('span');
            meta.className = 'tool-bubble-meta';
            meta.textContent = ` · ${resultInfo.info.delivered_chars.toLocaleString()} chars` +
              (resultInfo.info.truncated ? ' (truncated)' : '');
            row.querySelector('.tool-bubble-title').appendChild(meta);
          }
          row.classList.add('has-result');
        }
        updateTurnCounts(msg);
        noteActivity(msg);
      } catch (e) {}
      break;
    }

    case 'heartbeat': {
      try {
        const info = JSON.parse(data);
        // Seat lifecycle notices persist in the transcript; a transient
        // pulse was missed in live use.
        if (info.phase === 'seated' || info.phase === 'unknown-seat') {
          appendNoticeChip(info.label, info.phase === 'unknown-seat');
          if (info.phase === 'seated') loadSeats();
        } else if (info.label) {
          setActivityPulse(msg, info.label);
        }
      } catch (e) {
        setActivityPulse(msg, 'Working…');
      }
      break;
    }

    case 'done':
      finalizeAgentMessage();
      break;
  }
}

// Stable accent per seat id so a seat keeps its color across rounds.
function seatAccent(speaker) {
  let hash = 0;
  for (let i = 0; i < speaker.length; i++) hash = (hash * 31 + speaker.charCodeAt(i)) | 0;
  return 'seat-accent-' + (Math.abs(hash) % 4);
}

function appendRoundDivider(data) {
  let label = 'round';
  try { label = 'round ' + (JSON.parse(data).round || ''); } catch (e) {}
  const div = document.createElement('div');
  div.className = 'round-divider';
  div.innerHTML = `<span>${escapeHtml(label)}</span>`;
  messagesContainer.appendChild(div);
  scrollToBottom();
}

// --- Mission control (SPEC-GROUP-CHAT-V1 G8): GET /agents polling ---

let missionTimer = null;

function toggleMissionControl() {
  const panel = document.getElementById('mission-panel');
  if (!panel) return;
  const opening = panel.classList.contains('hidden');
  panel.classList.toggle('hidden');
  if (opening) {
    // the panel lives in the rail, so opening it opens the rail
    if (!mainLayout.classList.contains('rail-open')) setRailOpen(true);
    renderMissionRows();
    missionTimer = setInterval(renderMissionRows, 2000);
  } else if (missionTimer) {
    clearInterval(missionTimer);
    missionTimer = null;
  }
}
async function renderMissionRows() {
  const holder = document.getElementById('mission-rows');
  if (!holder) return;
  try {
    const body = await (await fetch(`${API_BASE}/agents`)).json();
    const rows = body.agents || [];
    if (rows.length === 0) {
      holder.innerHTML = '<div class="mission-empty">No live turns</div>';
      return;
    }
    holder.innerHTML = rows.map(r => {
      const secs = Math.max(0, Math.round(Date.now() / 1000 - r.started));
      const repo = (r.cwd || '').split('/').pop();
      const subs = (r.subagents || []).map(s => `
        <div class="mission-sub">
          <span class="mission-state">${escapeHtml(s.state)}</span>
          <span>subagent${s.tool ? ' · ' + escapeHtml(s.tool) : ''}</span>
        </div>`).join('');
      return `
      <div class="mission-row">
        <div class="mission-main">
          <span class="mission-name">${escapeHtml(r.name)}${r.prep ? ' <em>prep</em>' : ''}</span>
          <span class="mission-state">${escapeHtml(r.state)}${r.tool ? ' · ' + escapeHtml(r.tool) : ''}</span>
          <span class="mission-meta">${escapeHtml(repo)} · ${secs}s${r.kb_file ? '  ' + escapeHtml(r.kb_file.split('/').pop()) : ''}</span>
        </div>${subs}
      </div>`;
    }).join('');
  } catch (err) { /* poll again next tick */ }
}

// G10 prep: mark the seat's roster row while it researches in parallel.
function notePrepActivity(p) {
  if (!p.speaker) return;
  const row = document.querySelector(
    `#seat-list .seat-row[data-seat='${CSS.escape(p.speaker)}']`);
  if (!row) return;
  row.classList.add('prepping');
  row.title = 'prepping' + (p.tool ? ': ' + p.tool : '');
}

function clearPrepIndicators(speaker) {
  const scope = speaker
    ? `#seat-list .seat-row.prepping[data-seat='${CSS.escape(speaker)}']`
    : '#seat-list .seat-row.prepping';
  document.querySelectorAll(scope).forEach(row => {
    row.classList.remove('prepping');
    row.removeAttribute('title');
  });
}

function appendNoticeChip(label, warn) {
  if (!label) return;
  const chip = document.createElement('div');
  chip.className = 'seat-notice-chip' + (warn ? ' notice-warn' : '');
  chip.textContent = label;
  messagesContainer.appendChild(chip);
  scrollToBottom();
}

function handleSeatDone(data) {
  // A pass leaves no trace in the transcript: the passed seat's bubble holds
  // only "PASS" (or nothing), so it is dropped. For a seat that did speak,
  // strip an appended PASS from the live bubble - the same protocol-leakage
  // rule the server applies to the persisted turn. Returns true when the
  // bubble was removed, so the stream loop can forget it as currentMsg.
  try {
    const info = JSON.parse(data);
    const bubbles = messagesContainer.querySelectorAll(
      `.message.agent[data-speaker='${info.speaker}']`);
    const last = bubbles[bubbles.length - 1];
    if (!last) return false;
    // Settle the bubble before judging it: the seat's turn is over, so the
    // idle "Thinking…" pulse and the debounced markdown render must not be
    // part of the text - a pulse inside the content kept passed bubbles
    // alive and pulsing through the NEXT seat's whole turn (UAT 2026-09-07).
    last.classList.remove('streaming');
    if (last._idleWatcher) {
      clearTimeout(last._idleWatcher);
      last._idleWatcher = null;
    }
    setStreamingCursor(last, false);
    setActivityPulse(last, null);
    last.querySelectorAll('.iteration-text').forEach((textEl) => {
      if (textEl._renderTimer) {
        clearTimeout(textEl._renderTimer);
        textEl._renderTimer = null;
        textEl.innerHTML = renderMarkdown(stripToolMarkers(textEl._rawText || ''));
      }
    });
    if (info.passed) {
      const content = last.querySelector('.message-content');
      const text = (content ? content.innerText : '').replace(/▌/g, '').trim();
      if (text === '' || text === 'PASS') {
        if (last._feed) last._feed.remove();
        last.remove();
        return true;
      }
      return false;
    }
    let target = null;
    last.querySelectorAll('*').forEach((n) => { if (n._rawText) target = n; });
    const raw = target ? target._rawText.trimEnd() : '';
    if (raw.endsWith('PASS') && raw.length > 4
        && !/[A-Za-z0-9]/.test(raw[raw.length - 5])) {
      target._rawText = raw.slice(0, -4).trimEnd();
      target.innerHTML = renderMarkdown(target._rawText);
    }
  } catch (e) {}
  return false;
}

function createAgentMessage(speaker, speakerName) {
  const div = document.createElement('div');
  div.className = 'message agent streaming';
  div.dataset.turn = String(++turnCounter);
  if (speaker) {
    div.dataset.speaker = speaker;
    div.classList.add(seatAccent(speaker));
  }
  const label = speakerName || speaker || 'B';
  div.innerHTML = `
    <div class="speaker-chip">${escapeHtml(label)}</div>
    <div class="message-content"></div>
    <div class="message-actions">
      <button class="message-action-btn" title="Copy" data-action="copy-message">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
        </svg>
      </button>
    </div>
  `;
  messagesContainer.appendChild(div);
  scrollToBottom();
  return div;
}

function appendKBResult(path, score) {
  showActivity(`KB: ${path.split('/').pop()} (score: ${score})`);
}

function appendUserMessage(content) {
  // Finalize any previous streaming agent messages so their "Thinking…"
  // indicators don't linger when the user sends a new message.
  messagesContainer.querySelectorAll('.message.agent.streaming').forEach((msg) => {
    msg.classList.remove('streaming');
    if (msg._idleWatcher) {
      clearTimeout(msg._idleWatcher);
      msg._idleWatcher = null;
    }
    setActivityPulse(msg, null);
    setStreamingCursor(msg, false);
  });

  const div = document.createElement('div');
  div.className = 'message user';
  const contentEl = document.createElement('div');
  contentEl.className = 'message-content';
  contentEl.textContent = content;
  div.innerHTML = `
    <div class="message-actions">
      <button class="message-action-btn" title="Copy" data-action="copy-message">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2 2v1"></path>
        </svg>
      </button>
    </div>
  `;
  div.insertBefore(contentEl, div.querySelector('.message-actions'));
  messagesContainer.appendChild(div);
  scrollToBottom(true);  // a send always snaps the view to the thread tail
}

function appendAgentChunk(content) {
  let lastMsg = messagesContainer.lastElementChild;
  if (!lastMsg || !lastMsg.classList.contains('agent')) {
    const div = document.createElement('div');
    div.className = 'message agent streaming';
    div.dataset.turn = String(++turnCounter);
    div.innerHTML = `
      <div class="speaker-chip">brain</div>
      <div class="message-content"></div>
      <div class="message-actions">
        <button class="message-action-btn" title="Copy" data-action="copy-message">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2 2v1"></path>
          </svg>
        </button>
      </div>
    `;
    messagesContainer.appendChild(div);
    lastMsg = div;
  }
  const contentEl = lastMsg.querySelector('.message-content');
  contentEl._rawText = (contentEl._rawText || '') + content;
  if (!contentEl._renderTimer) {
    contentEl._renderTimer = setTimeout(() => {
      contentEl.innerHTML = renderMarkdown(contentEl._rawText) + '<span class="streaming-cursor">▌</span>';
      contentEl._renderTimer = null;
      scrollToBottom();
    }, 150);
  }
}

async function finalizeAgentMessage() {
  // Finalize EVERY streaming agent message, not just the last DOM child -
  // in a group round a notice chip or round divider lands after a seat's
  // bubble, and finalizing only lastElementChild left the bubble stuck
  // streaming ("Thinking…" forever).
  const streamers = messagesContainer.querySelectorAll('.message.agent.streaming');
  for (const lastMsg of streamers) {
    lastMsg.classList.remove('streaming');
    if (lastMsg._idleWatcher) {
      clearTimeout(lastMsg._idleWatcher);
      lastMsg._idleWatcher = null;
    }
    setStreamingCursor(lastMsg, false);
    setActivityPulse(lastMsg, null);
    if (!lastMsg.querySelector('.message-actions')) {
      const actionsDiv = document.createElement('div');
      actionsDiv.className = 'message-actions';
      actionsDiv.innerHTML = `
        <button class="message-action-btn" title="Copy" data-action="copy-message">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2 2v1"></path>
          </svg>
        </button>
      `;
      lastMsg.appendChild(actionsDiv);
    }
    // The feed section settles: counts final, any still-running row stopped.
    if (lastMsg._feed) {
      lastMsg._feed.querySelectorAll('.tool-call-bubble.running').forEach((row) => {
        stopToolTimer(row);
        row.classList.remove('running');
      });
      lastMsg._feed.classList.add('done');
      updateTurnCounts(lastMsg);
    }
    const iterations = lastMsg.querySelectorAll('.iteration');
    iterations.forEach((iter) => {
      const textEl = iter.querySelector('.iteration-text');
      if (textEl && textEl._rawText) {
        if (textEl._renderTimer) {
          clearTimeout(textEl._renderTimer);
          textEl._renderTimer = null;
        }
        textEl.innerHTML = renderMarkdown(stripToolMarkers(textEl._rawText));
        delete textEl._rawText;
      }
    });
    // Back-compat: if the message has no iterations (e.g. legacy server)
    // but has buffered raw text on the content element, render it.
    const contentEl = lastMsg.querySelector('.message-content');
    if (contentEl && contentEl._rawText && iterations.length === 0) {
      if (contentEl._renderTimer) {
        clearTimeout(contentEl._renderTimer);
        contentEl._renderTimer = null;
      }
      contentEl.innerHTML = renderMarkdown(stripToolMarkers(contentEl._rawText));
      delete contentEl._rawText;
    }
    await renderMermaidDiagrams(lastMsg);
  }
}

async function renderMermaidDiagrams(container) {
  if (!mermaidModule) return;
  const mermaidElements = container.querySelectorAll('pre.mermaid');
  if (mermaidElements.length === 0) return;
  for (const el of Array.from(mermaidElements)) {
    try {
      const id = 'mm-' + Math.random().toString(36).slice(2, 9);
      const { svg } = await mermaidModule.render(id, el.textContent);
      const wrapper = document.createElement('div');
      wrapper.className = 'mermaid-svg-wrapper';
      wrapper.style.cssText = 'overflow:auto;max-width:100%;';
      wrapper.innerHTML = svg;
      // Defense in depth behind securityLevel:'strict' - the diagram
      // source is model-authored, so the rendered SVG is scrubbed of
      // event handlers and script-bearing URLs before it goes live.
      sanitizeRenderedSvg(wrapper);
      el.replaceWith(wrapper);
    } catch (e) {
      console.error('Mermaid render error:', e);
    }
  }
}

function appendAgentMessage(content, speaker, speakerName) {
  const div = document.createElement('div');
  div.className = 'message agent';
  if (speaker) {
    div.dataset.speaker = speaker;
    div.classList.add(seatAccent(speaker));
  }
  const label = speakerName || speaker || 'B';
  div.innerHTML = `
    <div class="speaker-chip">${escapeHtml(label)}</div>
    <div class="message-content">${renderMarkdown(content)}</div>
    <div class="message-actions">
      <button class="message-action-btn" title="Copy" data-action="copy-message">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2 2v1"></path>
        </svg>
      </button>
    </div>
  `;
  messagesContainer.appendChild(div);
  scrollToBottom();
}

let _scrollQueued = false;

function scrollToBottom(force) {
  // The SCROLLER is #chat-container - #messages is the inner column and
  // never scrolls (live 2026-08-27: following silently depended on the
  // browser's own bottom-anchoring, which is what felt clunky).
  const scroller = document.getElementById('chat-container');
  if (!scroller) return;
  // Damped follow: only follow when the reader is already near the
  // bottom; scrolling up to read pins the view until they return.
  // Coalesced to one scroll per frame - per-token jumps read as jitter.
  const nearBottom = scroller.scrollHeight
    - scroller.scrollTop - scroller.clientHeight < 220;
  if (!force && !nearBottom) return;
  if (_scrollQueued) return;
  _scrollQueued = true;
  requestAnimationFrame(() => {
    _scrollQueued = false;
    scroller.scrollTop = scroller.scrollHeight;
  });
}

// File Browser
function toggleSection(header) {
  const section = header.closest('.sidebar-section.collapsible');
  if (!section) return;
  section.classList.toggle('collapsed');
  const key = 'sidebar_section_' + section.dataset.section;
  localStorage.setItem(key, section.classList.contains('collapsed'));
}
function loadFileList() {
  fetch(`${API_BASE}/kb/tree`)
    .then(r => r.json())
    .then(tree => {
      if (folderTree) {
        folderTree.innerHTML = renderRoot(tree);
      }
    });
}

// The vault root renders as its own collapsible folder (default open);
// every folder below it defaults closed.
function renderRoot(tree) {
  const isExpanded = localStorage.getItem('brain_folder_/') !== '0';
  const total = countFiles(tree);
  return `
    <div class="folder-item ${isExpanded ? '' : 'collapsed'}" data-folder-path="/">
      <div class="folder-header" data-action="toggle-folder">
        <svg class="folder-chevron" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="6 9 12 15 18 9"></polyline></svg>
        <svg class="folder-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
        <span class="folder-name">vault</span>
        <span style="margin-left:auto;font-size:0.6rem;color:var(--text-muted)">${total}</span>
      </div>
      <div class="folder-children">${renderTree(tree, 1)}</div>
    </div>
  `;
}

function countFiles(node) {
  return node.files.length + node.dirs.reduce((n, d) => n + countFiles(d), 0);
}

// Recursive renderer over /kb/tree's {name, path, dirs, files} shape.
// Expand state is keyed on the folder's vault-relative path; folders
// default closed until explicitly expanded.
function renderTree(node, depth) {
  const indent = depth * 12;
  const dirEls = node.dirs.map(d => {
    const isExpanded = localStorage.getItem('brain_folder_' + d.path) === '1';
    return `
      <div class="folder-item ${isExpanded ? '' : 'collapsed'}" data-folder-path="${escapeHtml(d.path)}">
        <div class="folder-header" data-action="toggle-folder" style="padding-left:${indent}px">
          <svg class="folder-chevron" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="6 9 12 15 18 9"></polyline></svg>
          <svg class="folder-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
          <span class="folder-name">${escapeHtml(d.name)}</span>
          <svg class="folder-graph-btn" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
               data-graph-path="${escapeHtml(d.path)}"
               style="margin-left:auto;cursor:pointer;opacity:0.45" title="View this folder's graph">
            <circle cx="5" cy="6" r="2.2"></circle><circle cx="18" cy="5" r="2.2"></circle><circle cx="12" cy="18" r="2.2"></circle>
            <line x1="6.8" y1="7.4" x2="10.6" y2="16.2"></line><line x1="16.6" y1="6.6" x2="13.3" y2="16.2"></line>
          </svg>
          <span style="margin-left:6px;font-size:0.6rem;color:var(--text-muted)">${d.files.length}</span>
        </div>
        <div class="folder-children">${renderTree(d, depth + 1)}</div>
      </div>
    `;
  }).join('');

  const fileEls = node.files.map(f => `
    <div class="file-item" data-path="${escapeHtml(f.path)}" style="padding-left:${indent + 20}px">
      <svg class="file-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
      <span class="file-name">${escapeHtml(f.name)}</span>
    </div>
  `).join('');

  return dirEls + fileEls;
}
function toggleFolder(header) {
  const folderItem = header.closest('.folder-item');
  if (!folderItem) return;
  folderItem.classList.toggle('collapsed');
  localStorage.setItem('brain_folder_' + folderItem.dataset.folderPath,
    folderItem.classList.contains('collapsed') ? '0' : '1');
}
// kb-graph-hud.js calls this as window.loadFile when a graph node is
// clicked. It resolves because app.js is a classic script and top-level
// declarations land on window - wrapping this file in a module or an
// IIFE would degrade that call to a silent no-op behind the hud's typeof
// guard, so the coupling is named here rather than left implicit.
function loadFile(path, heading) {
  // Track recent file
  recentFiles = recentFiles.filter(f => f !== path);
  recentFiles.unshift(path);
  if (recentFiles.length > MAX_RECENT_FILES) recentFiles = recentFiles.slice(0, MAX_RECENT_FILES);
  localStorage.setItem('brain_recent_files', JSON.stringify(recentFiles));
  renderRecentFiles();

  fetch(`${API_BASE}/kb/file/${encodeURIComponent(path)}`)
    .then(r => {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.text();
    })
    .then(async content => {
      const viewer = document.getElementById('file-viewer');
      const title = document.getElementById('file-viewer-title');
      const body = document.getElementById('file-viewer-content');
      if (!viewer) return;
      title.textContent = path;
      body.innerHTML = renderMarkdown(content);
      viewer.classList.remove('hidden');
      viewer.scrollTop = 0;
      await renderMermaidDiagrams(body);
      // Graph-card click-through lands on the section (STORY-000068).
      if (heading) {
        const want = heading.trim().toLowerCase();
        const target = [...body.querySelectorAll('h1,h2,h3,h4,h5,h6')]
          .find(el => el.textContent.trim().toLowerCase() === want);
        if (target) target.scrollIntoView({ block: 'start' });
      }
    })
    .catch(err => {
      const viewer = document.getElementById('file-viewer');
      const title = document.getElementById('file-viewer-title');
      const body = document.getElementById('file-viewer-content');
      if (!viewer) return;
      title.textContent = path;
      body.innerHTML = `<div class="file-viewer-error">Could not load this file (${escapeHtml(err.message)}).</div>`;
      viewer.classList.remove('hidden');
    });
}

function closeFileViewer() {
  const viewer = document.getElementById('file-viewer');
  if (viewer) viewer.classList.add('hidden');
}
function renderRecentFiles() {
  if (!recentFilesList) return;
  if (recentFiles.length === 0) {
    recentFilesList.innerHTML = '<li style="color:var(--text-muted);font-style:italic;font-size:0.7rem">No recent files</li>';
    return;
  }
  // Name and folder derive from the vault-relative path directly.
  recentFilesList.innerHTML = recentFiles.map(path => {
    const name = path.split('/').pop();
    const folder = path.split('/').slice(0, -1).join('/');
    return `
      <li data-path="${escapeHtml(path)}">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
        <span class="file-name">${escapeHtml(name)}</span>
        <span style="margin-left:auto;font-size:0.6rem;color:var(--accent-dim)">${escapeHtml(folder)}</span>
      </li>
    `;
  }).join('');
}

// Search
let searchDebounce = null;

let searchScope = localStorage.getItem('brain_search_scope') || 'content';

function doSearch(query) {
  if (!query) {
    searchResults.innerHTML = '';
    return;
  }
  fetch(`${API_BASE}/kb/search?q=${encodeURIComponent(query)}&scope=${searchScope}`)
    .then(r => r.json())
    .then(results => {
      if (results.length === 0) {
        searchResults.innerHTML = '<div style="color:var(--text-muted);font-size:0.72rem;padding:8px">No results found</div>';
        return;
      }
      searchResults.innerHTML = results.slice(0, 8).map(r => {
        const folder = r.path ? r.path.split('/').slice(0, -1).join('/') : '';
        const filename = r.path ? r.path.split('/').pop() : '';
        return `
          <div class="search-result" data-path="${escapeHtml(r.path)}">
            <div class="search-result-path">${folder ? escapeHtml(folder + '/') : ''}${escapeHtml(filename)}</div>
            <div class="search-result-title">${escapeHtml(r.heading || filename)}</div>
            <div class="search-result-snippet">${escapeHtml(r.snippet || '')}</div>
            <div class="search-result-meta">
              <span>${r.score ? 'score: ' + r.score.toFixed(2) : ''}</span>
              <span>${r.tier || ''}</span>
            </div>
          </div>
        `;
      }).join('');
    });
}

// Index Stats
function loadIndexStats() {
  fetch(`${API_BASE}/kb/stats`)
    .then(r => {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(stats => {
      const fileCount = document.getElementById('file-count');
      const vectorCount = document.getElementById('section-count');
      const graphNodes = document.getElementById('edge-count');
      if (fileCount) fileCount.textContent = stats.files || 0;
      if (vectorCount) vectorCount.textContent = stats.sections || 0;
      if (graphNodes) graphNodes.textContent = stats.edges || 0;
    })
    .catch(err => console.error('loadIndexStats failed:', err));
}

function toggleGraphHUD() {
  const hud = document.getElementById('kb-graph-hud');
  if (!hud) {
    alert('Graph HUD not initialized yet. Start a conversation to activate it.');
    return;
  }
  const hidden = hud.style.display === 'none';
  hud.style.display = hidden ? 'block' : 'none';
  localStorage.setItem('brain_graph_hud_visible', hidden ? '1' : '0');
}
// Sidebar folder graph glyph: swap the HUD to that folder's scoped view
// (R34). Empty scope resets to the whole vault.
function viewFolderGraph(scope) {
  const hud = document.getElementById('kb-graph-hud');
  if (hud && hud.style.display === 'none') toggleGraphHUD();
  if (typeof window.kbGraphScope === 'function') window.kbGraphScope(scope);
}
// Event Listeners
function setupEventListeners() {
  if (sendBtn) sendBtn.addEventListener('click', sendMessage);
  if (textInput) {
    textInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
    textInput.addEventListener('input', () => {
      textInput.style.height = 'auto';
      textInput.style.height = textInput.scrollHeight + 'px';
    });
  }

  if (searchInput) searchInput.addEventListener('input', (e) => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => doSearch(e.target.value), 300);
  });

  if (reindexBtn) reindexBtn.addEventListener('click', () => {
    const entities = document.getElementById('reindex-entities')?.checked || false;
    const body = { entities };
    reindexBtn.disabled = true;
    const originalText = reindexBtn.innerHTML;
    reindexBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation:spin 1s linear infinite"><circle cx="12" cy="12" r="10" stroke-dasharray="60" stroke-dashoffset="20"></circle></svg> Rebuilding...`;
    fetch(`${API_BASE}/kb/reindex`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
      .then(r => r.json())
      .then(data => {
        loadIndexStats();
        loadFileList();
        renderRecentFiles();
        const parts = ['Index rebuilt'];
        if (entities) parts.push('with entities');
        alert(parts.join(' '));
      })
      .catch(err => alert('Reindex failed: ' + err.message))
      .finally(() => {
        reindexBtn.disabled = false;
        reindexBtn.innerHTML = originalText;
      });
  });

  if (modelSelect) modelSelect.addEventListener('change', (e) => {
    const model = e.target.value.trim();
    if (model) switchModel(model);
  });
  const claudeModelEl = document.getElementById('claude-model-select');
  const claudeEffortEl = document.getElementById('claude-effort-select');
  if (claudeModelEl) claudeModelEl.addEventListener('change', saveClaudeSettings);
  if (claudeEffortEl) claudeEffortEl.addEventListener('change', saveClaudeSettings);
  if (modelSelect) modelSelect.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const model = e.target.value.trim();
      if (model) switchModel(model);
    }
  });

  // Search scope toggle: contents (engine FTS) vs file names (path keywords)
  document.querySelectorAll('#search-scope .tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.scope === searchScope);
    tab.addEventListener('click', (e) => {
      document.querySelectorAll('#search-scope .tab').forEach(t => t.classList.remove('active'));
      e.target.classList.add('active');
      searchScope = e.target.dataset.scope;
      localStorage.setItem('brain_search_scope', searchScope);
      if (searchInput && searchInput.value) doSearch(searchInput.value);
    });
  });

  if (sidebarToggle && sidebar && mainLayout) {
    sidebarToggle.addEventListener('click', () => {
      sidebar.classList.toggle('collapsed');
      mainLayout.classList.toggle('sidebar-collapsed');
      localStorage.setItem('sidebar_collapsed', sidebar.classList.contains('collapsed'));
    });
  }

  // Ctrl+J / Cmd+J toggles the activity rail from anywhere, composer included.
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'j') {
      e.preventDefault();
      toggleRail();
    }
  });
}

// Activity status: one line in the rail header. It used to be a bar
// inserted above the composer, which shrank the transcript on every send.
function showActivity(text) {
  const status = document.getElementById('rail-status');
  if (!status) return;
  status.textContent = text;
  status.parentElement.classList.add('busy');
}

function hideActivity() {
  const status = document.getElementById('rail-status');
  if (!status) return;
  status.textContent = 'Idle';
  status.parentElement.classList.remove('busy');
}

// Utilities
//
// Safe for text between tags and for QUOTED DATA attributes. NOT safe for
// on* handler attributes, and no amount of escaping makes it so: the HTML
// parser decodes entities in an attribute value BEFORE the handler body is
// compiled as JavaScript, so &#39; becomes a real apostrophe inside the
// script and closes the string anyway. That is why every interpolated
// inline handler in this file was replaced with a data attribute and a
// delegated listener rather than escaped harder - two of them were
// verified executing from agent-authored vault names (2026-08-29).
// Quotes are escaped here so the helper is correct in data-attribute
// position; if you find yourself reaching for it inside an on* attribute,
// the answer is a data attribute instead.
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text == null ? '' : text;
  return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function copyMessage(btn) {
  const message = btn.closest('.message');
  const content = message.querySelector('.message-content').innerText;
  navigator.clipboard.writeText(content).then(() => {
    const originalIcon = btn.innerHTML;
    btn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="20 6 9 17 4 12"></polyline>
      </svg>
    `;
    setTimeout(() => {
      btn.innerHTML = originalIcon;
    }, 1500);
  });
}