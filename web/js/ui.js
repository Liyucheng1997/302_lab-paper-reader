// 通用 UI：图标、转义、提示、弹窗、Markdown、论文卡片
const P = {
  compass: '<circle cx="12" cy="12" r="10"/><path d="m16.24 7.76-2.12 6.36-6.36 2.12 2.12-6.36 6.36-2.12z"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  bookmark: '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>',
  sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M2 14h4M10 8h4M18 16h4"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2m-7.07-14.07 1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
  sparkles: '<path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.14-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.14a.5.5 0 0 1 .96 0l1.58 6.14a2 2 0 0 0 1.44 1.44l6.14 1.58a.5.5 0 0 1 0 .96l-6.14 1.58a2 2 0 0 0-1.44 1.44l-1.58 6.14a.5.5 0 0 1-.96 0z"/>',
  message: '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  plus: '<path d="M5 12h14M12 5v14"/>',
  external: '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4M16 13H8M16 17H8M10 9H8"/>',
  back: '<path d="m12 19-7-7 7-7M19 12H5"/>',
  trash: '<path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
  send: '<path d="M12 19V5M5 12l7-7 7 7"/>',
  book: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  edit: '<path d="M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  chevron: '<path d="m9 18 6-6-6-6"/>',
  panel: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M15 3v18"/>',
  globe: '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20M2 12h20"/>',
  tree: '<path d="M21 12h-8M21 6H8M21 18h-8M3 6v4c0 1.1.9 2 2 2h3M3 10v6c0 1.1.9 2 2 2h3"/>',
  target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
  copy: '<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  translate: '<path d="m5 8 6 6M4 14l6-6 2-3M2 5h12M7 2h1M22 22l-5-10-5 10M14 18h6"/>',
  help: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01"/>',
  layers: '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65M22 12.65l-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
  flask: '<path d="M10 2v7.31M14 9.3V1.99M8.5 2h7M14 9.3a6.5 6.5 0 1 1-4 0M5.52 16h12.96"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
  route: '<circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/>',
  bulb: '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5M9 18h6M10 22h4"/>',
  eyeoff: '<path d="M9.88 9.88a3 3 0 1 0 4.24 4.24M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68M6.61 6.61A13.53 13.53 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61M2 2l20 20"/>',
};

export function icon(name, size = 18, extra = '') {
  return `<svg class="ico ico-${size} ${extra}" viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${P[name] || ''}</svg>`;
}

export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export function h(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ---------- 提示 ----------
export function toast(msg, type = '') {
  const host = document.getElementById('toasts');
  const el = h(`<div class="toast ${type ? 'toast-' + type : ''}">${esc(msg)}</div>`);
  host.appendChild(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.remove(), 300); }, type === 'error' ? 4200 : 2400);
}

// ---------- 弹窗 ----------
export function modal({ title, body, footer, width, onClose }) {
  const overlay = h(`<div class="modal-overlay"><div class="modal" style="${width ? `width:${width}px` : ''}">
    <div class="modal-header"><span>${esc(title)}</span><button class="modal-x" data-close>${icon('x', 14)}</button></div>
    <div class="modal-body"></div>
    ${footer !== false ? '<div class="modal-footer"></div>' : ''}
  </div></div>`);
  const bodyEl = $('.modal-body', overlay);
  if (typeof body === 'string') bodyEl.innerHTML = body; else if (body) bodyEl.appendChild(body);
  const close = () => { overlay.remove(); document.removeEventListener('keydown', onKey); onClose && onClose(); };
  const onKey = e => { if (e.key === 'Escape') close(); };
  overlay.addEventListener('mousedown', e => { if (e.target === overlay) close(); });
  $('[data-close]', overlay).onclick = close;
  document.addEventListener('keydown', onKey);
  if (footer && footer.length) {
    const f = $('.modal-footer', overlay);
    for (const b of footer) {
      const btn = h(`<button class="btn ${b.cls || ''}">${esc(b.label)}</button>`);
      btn.onclick = () => b.onClick(close, btn);
      if (b.left) btn.style.marginRight = 'auto';
      f.appendChild(btn);
    }
  }
  document.body.appendChild(overlay);
  return { el: overlay, body: bodyEl, close };
}

export function confirmDialog(title, message, { okLabel = '确定', danger = false } = {}) {
  return new Promise(resolve => {
    let done = false;
    const m = modal({
      title, width: 400,
      body: `<div class="modal-msg">${esc(message)}</div>`,
      footer: [
        { label: '取消', onClick: c => { done = true; c(); resolve(false); } },
        { label: okLabel, cls: danger ? 'btn-primary danger-fill' : 'btn-primary', onClick: c => { done = true; c(); resolve(true); } },
      ],
      onClose: () => { if (!done) resolve(false); },
    });
    if (danger) $('.danger-fill', m.el).style.background = 'var(--danger)';
  });
}

export function promptDialog(title, value = '', placeholder = '') {
  return new Promise(resolve => {
    let done = false;
    const input = h(`<input class="input" style="width:100%;height:36px" placeholder="${esc(placeholder)}">`);
    input.value = value;
    const ok = c => { done = true; c(); resolve(input.value.trim()); };
    const m = modal({
      title, width: 400, body: input,
      footer: [
        { label: '取消', onClick: c => { done = true; c(); resolve(null); } },
        { label: '确定', cls: 'btn-primary', onClick: ok },
      ],
      onClose: () => { if (!done) resolve(null); },
    });
    input.addEventListener('keydown', e => { if (e.key === 'Enter') ok(m.close); });
    setTimeout(() => input.focus(), 30);
  });
}

// ---------- Markdown（轻量） ----------
export function md(src) {
  const store = [];
  const keep = s => `\u0000${store.push(s) - 1}\u0000`;
  let text = String(src ?? '').replace(/\r\n/g, '\n');
  // 代码块
  text = text.replace(/```(\w*)\n([\s\S]*?)(```|$)/g, (_, lang, code) => keep(`<pre><code>${esc(code.replace(/\n$/, ''))}</code></pre>`));
  // 数学公式保持原样，交给 KaTeX
  text = text.replace(/\$\$([\s\S]+?)\$\$/g, m => keep(`<div class="math-block">${esc(m)}</div>`));
  text = text.replace(/\\\[([\s\S]+?)\\\]/g, m => keep(`<div class="math-block">${esc(m)}</div>`));
  text = text.replace(/\$(?!\s)([^\n$]+?)\$/g, m => keep(esc(m)));
  text = text.replace(/\\\(([\s\S]+?)\\\)/g, m => keep(esc(m)));
  text = text.replace(/`([^`\n]+)`/g, (_, c) => keep(`<code>${esc(c)}</code>`));

  const inline = s => esc(s)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  const lines = text.split('\n');
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    let m;
    if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
      const lv = Math.min(4, m[1].length + 1);
      out.push(`<h${lv}>${inline(m[2])}</h${lv}>`); i++; continue;
    }
    if (/^(-{3,}|\*{3,})\s*$/.test(line)) { out.push('<hr>'); i++; continue; }
    if (/^\s*>/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ''));
      out.push(`<blockquote>${md(buf.join('\n'))}</blockquote>`); continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      const cells = l => l.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
      const head = cells(line);
      i += 2;
      const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(cells(lines[i++]));
      out.push(`<table><thead><tr>${head.map(c => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`);
      continue;
    }
    if (/^\s*([-*+]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]/.test(line);
      const items = [];
      while (i < lines.length && (/^\s*([-*+]|\d+[.)])\s+/.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        const l = lines[i++];
        if (/^\s*([-*+]|\d+[.)])\s+/.test(l)) items.push(l.replace(/^\s*([-*+]|\d+[.)])\s+/, ''));
        else items[items.length - 1] += ' ' + l.trim();
      }
      const tag = ordered ? 'ol' : 'ul';
      out.push(`<${tag}>${items.map(it => `<li>${inline(it)}</li>`).join('')}</${tag}>`);
      continue;
    }
    if (/^\u0000\d+\u0000$/.test(line.trim())) { out.push(line.trim()); i++; continue; }
    const buf = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\s*>|\s*([-*+]|\d+[.)])\s+|```)/.test(lines[i])) buf.push(lines[i++]);
    out.push(`<p>${buf.map(inline).join('<br>')}</p>`);
  }
  let html = out.join('\n');
  for (let k = 0; k < 3; k++) html = html.replace(/\u0000(\d+)\u0000/g, (_, n) => store[+n]);
  return html;
}

export function renderMath(el) {
  if (!el || !window.renderMathInElement) return;
  try {
    window.renderMathInElement(el, {
      delimiters: [
        { left: '$$', right: '$$', display: true },
        { left: '\\[', right: '\\]', display: true },
        { left: '$', right: '$', display: false },
        { left: '\\(', right: '\\)', display: false },
      ],
      throwOnError: false,
      ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
    });
  } catch (e) { /* ignore */ }
}

// ---------- 格式化 ----------
export function fmtDuration(sec) {
  sec = Math.round(sec || 0);
  if (sec < 60) return `${sec} 秒`;
  const m = Math.round(sec / 60);
  if (m < 60) return `${m} 分钟`;
  return `${Math.floor(m / 60)} 小时 ${m % 60} 分`;
}

export function fmtTime(ts) {
  const d = new Date(ts * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export function dayLabel(ts) {
  const d = new Date(ts * 1000);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.round((today - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000);
  if (diff === 0) return '今天';
  if (diff === 1) return '昨天';
  if (diff < 7) return `${diff} 天前`;
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日`;
}

export const paperUrl = id => '#/paper/' + encodeURIComponent(id);

export function externalLinks(p) {
  const t = encodeURIComponent(p.title || '');
  return {
    scholar: `https://scholar.google.com/scholar?q=${t}`,
    researchgate: `https://www.researchgate.net/search/publication?q=${t}`,
    ieee: `https://ieeexplore.ieee.org/search/searchresult.jsp?queryText=${t}`,
    semantic: p.s2_id ? `https://www.semanticscholar.org/paper/${p.s2_id}` : `https://www.semanticscholar.org/search?q=${t}`,
  };
}

const ENGINE_NAMES = { arxiv: 'arXiv', s2: 'Semantic Scholar', openalex: 'OpenAlex', ieee: 'IEEE Xplore', scholar: 'Google Scholar', feed: '订阅' };
export const engineName = k => ENGINE_NAMES[k] || k;

// ---------- 论文卡片 ----------
export function paperCard(p, opt = {}) {
  const s = p.summary || {};
  const authors = (p.authors || []).slice(0, 6).join(', ') + ((p.authors || []).length > 6 ? ' 等' : '');
  const venue = p.venue && p.venue !== 'arXiv' ? p.venue : '';
  const meta = [
    `<span class="pc-src">${esc(p.source || '')}</span>`,
    venue ? `<span class="sep-dot pc-venue" title="${esc(venue)}">${esc(venue)}</span>` : '',
    p.published ? `<span class="sep-dot tabular">${esc(p.published)}</span>` : '',
    p.citations ? `<span class="sep-dot tabular">引用 ${p.citations}</span>` : '',
    opt.foundIn && p.found_in && p.found_in.length > 1 ? `<span class="sep-dot">${p.found_in.map(engineName).join(' / ')} 均收录</span>` : '',
  ].join('');
  let body = '';
  if (s.tldr) {
    body = `<p class="pc-tldr">${esc(s.tldr)}</p>`;
    if (opt.points && s.points && s.points.length) body += `<ul class="pc-points">${s.points.map(x => `<li>${esc(x)}</li>`).join('')}</ul>`;
  } else if (p.s2_tldr) {
    body = `<p class="pc-abs">${esc(p.s2_tldr)}</p>`;
  } else if (p.abstract) {
    body = `<p class="pc-abs">${esc(p.abstract)}</p>`;
  }
  const tags = (s.tags || []).slice(0, opt.compact ? 2 : 4).map(t => `<span class="tag">${esc(t)}</span>`).join('');
  const state = p._read ? '<span class="state">已读</span>' : '';
  const ai = p._analyzed ? '<span class="state blue">已解读</span>' : '';
  const el = h(`<article class="pcard" data-id="${esc(p.id)}">
    <div class="pc-meta">${meta}</div>
    <h3 class="pc-title">${esc(p.title)}</h3>
    ${authors && !opt.compact ? `<div class="pc-authors">${esc(authors)}</div>` : ''}
    ${body}
    ${opt.extra || ''}
    <div class="pc-foot">${tags}${state}${ai}
      <div class="pc-actions">
        ${opt.dismiss ? `<button class="icon-btn" data-act="dismiss" title="不感兴趣">${icon('eyeoff', 16)}</button>` : ''}
        <button class="icon-btn" data-act="open-ext" title="打开原文">${icon('external', 16)}</button>
        <button class="icon-btn ${p._fav ? 'fav-on' : ''}" data-act="fav" title="${p._fav ? '编辑收藏' : '收藏'}">${icon('star', 16)}</button>
      </div>
    </div>
  </article>`);
  if (p._fav) $('.pc-actions', el).classList.add('show');
  el.addEventListener('click', e => {
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (act === 'open-ext') { e.stopPropagation(); window.open(p.url, '_blank', 'noopener'); return; }
    if (act === 'fav') { e.stopPropagation(); opt.onFav && opt.onFav(p, el); return; }
    if (act === 'dismiss') { e.stopPropagation(); opt.onDismiss && opt.onDismiss(p, el); return; }
    if (e.target.closest('a')) return;
    location.hash = paperUrl(p.id);
  });
  return el;
}

export function skeletons(n = 4) {
  return `<div class="plist">${Array.from({ length: n }, () => '<div class="skeleton"></div>').join('')}</div>`;
}

export function emptyState(ic, text) {
  return `<div class="empty">${icon(ic, 34)}<div>${text}</div></div>`;
}
