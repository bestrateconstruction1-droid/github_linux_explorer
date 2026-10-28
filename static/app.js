'use strict';
const $ = id => document.getElementById(id);
const state = {path: '', hidden: false, sort: 'name', desc: false, entries: [], selected: null, home: '', searching: false};

// Build DOM with textContent only, so odd file names can never run as code.
function el(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === 'class') node.className = value; else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value); else node.setAttribute(key, value);
  }
  for (const kid of kids.flat()) if (kid != null) node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return node;
}
async function api(path, params = {}) {
  const res = await fetch('/api/' + path + '?' + new URLSearchParams(params));
  const data = await res.json().catch(() => ({error: 'Unexpected reply.'}));
  if (!res.ok) throw new Error(data.error || 'Something went wrong.');
  return data;
}
const size = n => n < 1024 ? n + ' B' : n < 1048576 ? (n / 1024).toFixed(1) + ' KB' : n < 1073741824 ? (n / 1048576).toFixed(1) + ' MB' : (n / 1073741824).toFixed(1) + ' GB';
const when = s => s ? new Date(s * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'}) : '';
function setSide(...kids) { $('side').replaceChildren(...kids.flat().filter(Boolean)); }
function notice(message) { const n = $('notice'); n.textContent = message || ''; n.hidden = !message; }
function setCommand(text) { $('cmdText').textContent = text; }

async function openDir(path) {
  try {
    const data = await api('list', {path, hidden: state.hidden ? '1' : '0'});
    state.path = data.path; state.entries = data.entries; state.selected = null; state.searching = false;
    $('pathInput').value = data.path; $('upBtn').disabled = !data.parent; $('clearSearch').hidden = true;
    setCommand(data.cd + ' && ' + data.command);
    notice(data.truncated ? 'This folder is very large, so only the first 5,000 items are shown.' : data.hidden_count && !state.hidden ? data.hidden_count + ' hidden item(s) not shown (names starting with a dot). Tick "Hidden files" to see them: ls -la' : '');
    render();
    setSide(el('p', {class: 'hint', text: 'Click a file to preview it, or a folder to open it. Everything here is read-only.'}));
  } catch (error) { notice(error.message); }
}
function sorted() {
  const key = state.sort, dir = state.desc ? -1 : 1;
  const rank = e => e.type === 'dir' ? 0 : 1;
  return [...state.entries].sort((a, b) => rank(a) - rank(b) || dir * (key === 'size' ? a.size - b.size : key === 'mtime' ? a.mtime - b.mtime : key === 'owner' ? a.owner.localeCompare(b.owner) : a.name.localeCompare(b.name, undefined, {sensitivity: 'base'})));
}
function render() {
  const head = (label, key) => el('th', {scope: 'col', onclick: () => { state.desc = state.sort === key ? !state.desc : false; state.sort = key; render(); }}, label + (state.sort === key ? (state.desc ? ' ▼' : ' ▲') : ''));
  const rows = sorted().map(entry => el('tr', {tabindex: '0', class: state.selected === entry.name ? 'sel' : '', onclick: () => choose(entry), onkeydown: e => { if (e.key === 'Enter') choose(entry); }},
    el('td', {class: 'name'}, el('span', {class: entry.type === 'dir' ? 'dir' : ''}, (entry.type === 'dir' ? '📁 ' : entry.type === 'link' ? '🔗 ' : '📄 ') + entry.name + (entry.type === 'dir' ? '/' : '')),
      entry.flags.some(f => !f.startsWith('Sticky')) ? el('span', {class: 'badge', title: entry.flags.join(' ')}, '⚠ notable') : null),
    el('td', {text: entry.type === 'dir' ? '—' : size(entry.size)}), el('td', {class: 'mode', text: entry.mode}), el('td', {text: entry.owner}), el('td', {text: when(entry.mtime)})));
  $('view').replaceChildren(state.entries.length ? el('table', {}, el('thead', {}, el('tr', {}, head('Name', 'name'), head('Size', 'size'), el('th', {scope: 'col', cursor: 'default'}, 'Permissions'), head('Owner', 'owner'), head('Modified', 'mtime'))), el('tbody', {}, rows)) : el('p', {class: 'empty', text: 'This folder is empty (or only has hidden items).'}));
}
function choose(entry) {
  state.selected = entry.name;
  const full = (state.path === '/' ? '' : state.path) + '/' + entry.name;
  if (entry.type === 'dir') return openDir(full);
  render(); showFile(full, entry);
}
function permBox(info) {
  if (!info || !info.perm) return null;
  const p = info.perm;
  return el('div', {class: 'perm'}, el('p', {}, el('strong', {text: info.mode}), ' → who can do what:'),
    el('p', {text: 'Owner (' + info.owner + '): ' + p.owner}), el('p', {text: 'Group (' + info.group + '): ' + p.group}), el('p', {text: 'Everyone else: ' + p.everyone}),
    p.flags.map(f => el('p', {class: 'flag', text: '⚠ ' + f})));
}
async function showFile(path) {
  try {
    const data = await api('preview', {path});
    setCommand(data.command);
    setSide(el('h3', {text: data.info.name}),
      el('dl', {}, el('dt', {text: 'Type'}), el('dd', {text: data.description || data.kind}), el('dt', {text: 'Size'}), el('dd', {text: size(data.info.size)}), el('dt', {text: 'Modified'}), el('dd', {text: when(data.info.mtime)}),
        data.info.link ? [el('dt', {text: 'Points to'}), el('dd', {text: data.info.link})] : null),
      permBox(data.info), data.note ? el('p', {class: 'hint', text: data.note}) : null,
      el('pre', {text: data.text || '(empty file)'}), data.truncated ? el('p', {class: 'hint', text: 'Showing the start of the file. In a terminal: less ' + path}) : null);
  } catch (error) {
    setSide(el('p', {class: 'notice', text: error.message}));
  }
}
async function runSearch(event) {
  event.preventDefault();
  const query = $('searchInput').value.trim(); if (!query) return;
  notice('Searching…');
  try {
    const data = await api('search', {root: state.path, q: query, mode: $('searchMode').value});
    state.searching = true; $('clearSearch').hidden = false; setCommand(data.command);
    notice((data.results.length ? data.results.length + ' result(s)' : 'Nothing found') + (data.limited ? ' (showing the first ' + data.results.length + ')' : '') + (data.timed_out ? ' · stopped early after a few seconds, try a smaller folder' : ''));
    $('view').replaceChildren(...(data.results.length ? data.results.map(hit => el('div', {class: 'hit', tabindex: '0', onclick: () => open(hit), onkeydown: e => { if (e.key === 'Enter') open(hit); }},
      el('div', {class: 'path', text: (hit.type === 'dir' ? '📁 ' : '📄 ') + hit.path + (hit.line ? ':' + hit.line : '')}), hit.text ? el('div', {class: 'snippet', text: hit.text}) : null)) : [el('p', {class: 'empty', text: 'No matches inside ' + data.root})]));
  } catch (error) { notice(error.message); }
  function open(hit) { if (hit.type === 'dir') return openDir(hit.path); const folder = hit.path.slice(0, hit.path.lastIndexOf('/')) || '/'; openDir(folder).then(() => { state.selected = hit.path.split('/').pop(); render(); showFile(hit.path); }); }
}
async function init() {
  const {places, home} = await api('places'); state.home = home;
  $('places').replaceChildren(...places.map(p => el('li', {}, el('button', {type: 'button', title: p.why + '\n' + p.command, onclick: () => openDir(p.path)}, p.label, el('small', {text: p.path})))));
  $('pathForm').addEventListener('submit', e => { e.preventDefault(); openDir($('pathInput').value); });
  $('upBtn').addEventListener('click', () => openDir(state.path.replace(/\/[^/]*$/, '') || '/'));
  $('hiddenBox').addEventListener('change', e => { state.hidden = e.target.checked; openDir(state.path); });
  $('searchForm').addEventListener('submit', runSearch);
  $('clearSearch').addEventListener('click', () => { $('searchInput').value = ''; openDir(state.path); });
  $('copyBtn').addEventListener('click', async () => { try { await navigator.clipboard.writeText($('cmdText').textContent); $('copyBtn').textContent = 'Copied'; setTimeout(() => $('copyBtn').textContent = 'Copy', 1200); } catch { /* clipboard unavailable */ } });
  openDir(home);
}
init().catch(error => notice(error.message));
