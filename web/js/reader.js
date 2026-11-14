// 阅读器：全文 / PDF / 概览 + AI 解读、伴读对话、相关推荐
import { ME, aiLabel, hasAI, openAiAccess } from './access.js';
import { api, chatStream } from './api.js';
import { openFavorite } from './favorite.js';
import { openLook } from './look.js';
import {
  $, $$, confirmDialog, emptyState, esc, externalLinks, h, icon, md, paperUrl, renderMath, toast,
} from './ui.js';

let R = null;

const QUICK = [
  '用通俗的话讲讲这篇论文在做什么',
  '核心创新点是什么？和已有方法相比好在哪？',
  '详细解释方法部分的关键公式和推导思路',
  '实验设计是否充分？结论可信吗？',
  '这篇论文有哪些局限？可以怎样改进？',
  '帮我整理成一份组会汇报提纲',
];

export function leaveReader() {
  if (!R) return;
  clearInterval(R.timer);
  const rest = Math.round((Date.now() - R.lastTick) / 1000);
  if (rest > 3 && document.visibilityState === 'visible') api.historyTick(R.id, rest).catch(() => {});
  if (R.abort) R.abort.abort();
  hideSelBar();
  closeMenu();
  document.body.classList.remove('ai-collapsed');
  R = null;
}

export async function renderReader(root, id) {
  leaveReader();
  root.innerHTML = `<div class="loading"><div class="spinner"></div>正在打开论文…</div>`;
  const d = await api.paper(id);
  const p = d.paper;
  R = {
    id: p.id, paper: p, fav: d.favorite, analysis: d.analysis, chat: d.chat, pdfUrl: d.pdf_url,
    tab: (d.pdf_url || p.arxiv_id) ? 'text' : 'info', aiTab: d.chat.length && !d.analysis ? 'chat' : 'analysis',
    ft: null, ftPromise: null, similar: null, selection: null, sending: false, abort: null,
    lastTick: Date.now(), timer: null,
  };
  if (d.paper.id !== id) history.replaceState(null, '', paperUrl(d.paper.id));
  api.historyOpen(p.id).catch(() => {});
  R.timer = setInterval(() => {
    if (!R) return;
    const now = Date.now();
    if (document.visibilityState === 'visible') api.historyTick(R.id, Math.round((now - R.lastTick) / 1000)).catch(() => {});
    R.lastTick = now;
  }, 20000);

  try { const w = localStorage.getItem('aiWidth'); if (w) document.documentElement.style.setProperty('--ai-w', w + 'px'); } catch (e) { /* ignore */ }

  const venue = p.venue && p.venue !== 'arXiv' ? p.venue : '';
  const el = h(`<div class="reader">
    <div class="reader-top">
      <button class="round" data-back title="返回">${icon('back')}</button>
      <div class="grow" style="padding:0 4px">
        <div class="reader-title" title="${esc(p.title)}">${esc(p.title)}</div>
        <div class="reader-sub">${esc([p.source, venue, p.published, (p.authors || []).slice(0, 3).join(', ') + ((p.authors || []).length > 3 ? ' 等' : '')].filter(Boolean).join(' · '))}</div>
      </div>
      <div class="seg" data-tab><button data-k="text">全文</button><button data-k="pdf">PDF</button><button data-k="info">概览</button></div>
      <button class="round ${R.fav ? 'fav-on' : ''}" data-fav title="收藏">${icon('star')}</button>
      <button class="round" data-more title="原文与外部链接">${icon('external')}</button>
      <button class="round" data-look title="外观：纸张颜色、字号">${icon('type')}</button>
      <button class="round" data-togai title="显示 / 隐藏 AI 助手">${icon('panel')}</button>
    </div>
    <div class="reader-body">
      <section class="pane read-pane"><div class="pane-body" data-read></div></section>
      <div class="resizer" data-resizer></div>
      <section class="pane ai-pane">
        <div class="pane-head">
          <div class="seg" data-aitab><button data-k="analysis">${'AI 解读'}</button><button data-k="chat">伴读对话</button><button data-k="related">相关论文</button></div>
        </div>
        <div class="pane-body" data-ai></div>
      </section>
    </div>
  </div>`);
  root.replaceChildren(el);

  $('[data-back]', el).onclick = () => (history.length > 1 ? history.back() : (location.hash = '#/'));
  $$('[data-tab] button', el).forEach(b => b.onclick = () => setTab(b.dataset.k));
  $$('[data-aitab] button', el).forEach(b => b.onclick = () => setAiTab(b.dataset.k));
  $('[data-fav]', el).onclick = () => openFavorite(p, fav => {
    R.fav = fav;
    $('[data-fav]', el).classList.toggle('fav-on', !!fav);
  });
  $('[data-more]', el).onclick = e => openMoreMenu(e.currentTarget);
  $('[data-togai]', el).onclick = () => document.body.classList.toggle('ai-collapsed');
  $('[data-look]', el).onclick = e => openLook(e.currentTarget);
  setupResizer($('[data-resizer]', el));

  setTab(R.tab);
  setAiTab(R.aiTab);
}

// ---------- 左侧阅读区 ----------
function setTab(k) {
  if (!R) return;
  R.tab = k;
  $$('[data-tab] button').forEach(b => b.classList.toggle('active', b.dataset.k === k));
  const box = $('[data-read]');
  hideSelBar();
  if (k === 'pdf') {
    if (!R.pdfUrl) {
      box.innerHTML = emptyState('file', `这篇论文没有开放获取的 PDF。<br><a href="${esc(R.paper.url)}" target="_blank" rel="noopener">到出版社页面阅读</a>，或在概览里用 Google Scholar / ResearchGate 查找全文。`);
      return;
    }
    box.innerHTML = `<div class="loading" style="position:absolute;inset:0;z-index:0"><div class="spinner"></div>正在下载 PDF…</div>`;
    const frame = h(`<iframe class="pdf-frame" style="position:relative;z-index:1" src="/api/pdf?id=${encodeURIComponent(R.id)}" title="PDF"></iframe>`);
    box.appendChild(frame);
    return;
  }
  if (k === 'info') { renderInfo(box); return; }
  renderFulltext(box);
}

function loadFulltext() {
  if (!R.ftPromise) {
    const id = R.id;
    R.ftPromise = api.fulltext(id).then(ft => { if (R && R.id === id) R.ft = ft; return ft; })
      .catch(e => { if (R) R.ftPromise = null; throw e; });
  }
  return R.ftPromise;
}

async function renderFulltext(box) {
  const id = R.id;
  if (!R.ft) {
    box.innerHTML = `<div class="loading"><div class="spinner"></div>正在获取并解析全文（arXiv HTML 或 PDF），首次打开约需 5–30 秒…</div>`;
  }
  let ft;
  try { ft = await loadFulltext(); } catch (e) {
    if (R && R.id === id && R.tab === 'text') box.innerHTML = emptyState('alert', '全文获取失败：' + esc(e.message));
    return;
  }
  if (!R || R.id !== id || R.tab !== 'text') return;
  const p = R.paper;
  const srcName = { 'arxiv-html': 'arXiv HTML 全文', pdf: 'PDF 解析全文', abstract: '仅摘要' }[ft.source] || ft.source;
  const pages = ft.blocks.filter(b => b.t === 'page').length;
  const heads = [];
  const parts = [];
  ft.blocks.forEach((b, i) => {
    if (b.t === 'h') {
      heads.push({ i, lv: b.lv, x: b.x });
      const tag = 'h' + Math.min(4, (b.lv || 1) + 1);
      parts.push(`<${tag} id="sec-${i}" data-h="${i}">${esc(b.x)}</${tag}>`);
    } else if (b.t === 'p') {
      parts.push(`<p>${esc(b.x)}</p>`);
    } else if (b.t === 'eq') {
      parts.push(`<div class="eq">${esc('$$' + b.x + '$$')}${b.n ? `<span class="eq-n">${esc(b.n)}</span>` : ''}</div>`);
    } else if (b.t === 'page' && b.n > 1) {
      parts.push(`<div class="pg">第 ${b.n} 页</div>`);
    }
  });
  const notice = ft.source === 'abstract'
    ? `<div class="notice" style="margin-bottom:18px">${icon('alert', 16)}<div>未能获取全文（没有开放获取的 PDF 或需要机构权限），下面只有摘要，AI 也只能基于摘要解读。可<a href="${esc(p.url)}" target="_blank" rel="noopener">打开出版社页面</a>阅读原文。</div></div>`
    : '';
  const el = h(`<div class="ft">
    <nav class="toc"><div class="toc-title">目录</div>${heads.map(x => `<a href="#" data-to="${x.i}" class="lv${x.lv}">${esc(x.x)}</a>`).join('')}</nav>
    <article class="ft-body">
      <header class="ft-head"><h1>${esc(p.title)}</h1>
        <div class="muted" style="margin-top:8px;font-size:13.5px;line-height:1.6">${esc((p.authors || []).join(', '))}</div>
        <div class="ft-src row-flex wrap"><span class="state ${ft.source === 'abstract' ? 'warn' : 'ok'}">${srcName}${pages ? ` · ${pages} 页` : ''}</span><span class="muted" style="font-size:12.5px">选中文字可让 AI 解释、翻译或提问</span></div>
      </header>
      ${notice}${parts.join('')}
    </article>
  </div>`);
  box.replaceChildren(el);
  lazyMath($('.ft-body', el), box);
  $$('.toc a', el).forEach(a => a.onclick = e => { e.preventDefault(); scrollToHeading(+a.dataset.to); });
  // 滚动高亮目录
  const toc = $('.toc', el);
  const hs = $$('[data-h]', el);
  let raf = 0;
  box.onscroll = () => {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => {
      const top = box.getBoundingClientRect().top + 60;
      let cur = null;
      for (const hh of hs) { if (hh.getBoundingClientRect().top <= top) cur = hh.dataset.h; else break; }
      $$('a', toc).forEach(a => a.classList.toggle('on', a.dataset.to === cur));
    });
    hideSelBar();
  };
  $('.ft-body', el).addEventListener('mouseup', () => setTimeout(onSelect, 10));
}

// 公式多的论文（上千个）一次全部排版会让页面卡住十几秒：只排版滚动到附近的段落
let mathObserver = null;
function lazyMath(body, scroller) {
  if (mathObserver) mathObserver.disconnect();
  const targets = [...body.children].filter(n => /\$|\\\(|\\\[/.test(n.textContent));
  if (!('IntersectionObserver' in window)) { renderMath(body); return; }
  mathObserver = new IntersectionObserver(entries => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      mathObserver.unobserve(e.target);
      renderMath(e.target);
    }
  }, { root: scroller, rootMargin: '1200px 0px' });
  targets.forEach(t => mathObserver.observe(t));
}

function scrollToHeading(i) {
  const target = document.getElementById('sec-' + i);
  const box = $('[data-read]');
  if (!target || !box) return;
  // 屏幕外段落用的是估计高度，跳过去后上方段落排版完高度会变：连续校正几帧直到对准
  let tries = 0;
  const align = () => {
    const off = target.getBoundingClientRect().top - box.getBoundingClientRect().top - 16;
    if (Math.abs(off) > 4 && tries++ < 12) {
      box.scrollTop += off;
      requestAnimationFrame(align);
    }
  };
  align();
  target.classList.add('hl');
  setTimeout(() => target.classList.remove('hl'), 1800);
}

// AI 解读里的章节名 → 原文标题
const normSec = s => String(s || '').toLowerCase().replace(/[^a-z0-9一-龥. ]+/g, ' ').replace(/\s+/g, ' ').trim();
const ROMAN = { i: 1, ii: 2, iii: 3, iv: 4, v: 5, vi: 6, vii: 7, viii: 8, ix: 9, x: 10 };
function secNumber(s) {
  const t = normSec(s).replace(/^(section|sec|第)\s*/, '');
  let m = t.match(/^(\d+(?:\.\d+)*)/);
  if (m) return m[1];
  m = t.match(/^([ivx]+)[.\s]/);
  if (m && ROMAN[m[1]]) return String(ROMAN[m[1]]);
  m = String(s).match(/(\d+(?:\.\d+)*)\s*节/);
  return m ? m[1] : null;
}

export async function jumpToSection(text) {
  if (!R) return;
  if (R.tab !== 'text') setTab('text');
  let ft;
  try { ft = await loadFulltext(); } catch (e) { return; }
  await new Promise(r => setTimeout(r, 60));
  const heads = ft.blocks.map((b, i) => ({ b, i })).filter(x => x.b.t === 'h');
  const num = secNumber(text);
  let best = null;
  if (num) best = heads.find(x => secNumber(x.b.x) === num);
  if (!best) {
    const words = normSec(text).split(' ').filter(w => w.length > 2);
    let bestScore = 0;
    for (const x of heads) {
      const hw = normSec(x.b.x);
      const score = words.filter(w => hw.includes(w)).length;
      if (score > bestScore) { bestScore = score; best = x; }
    }
  }
  if (best) scrollToHeading(best.i);
  else toast('原文中没有找到对应章节');
}

function renderInfo(box) {
  const p = R.paper;
  const s = p.summary || {};
  const L = externalLinks(p);
  const rows = [
    ['作者', (p.authors || []).join(', ')],
    ['来源', [p.source, p.venue && p.venue !== 'arXiv' ? p.venue : ''].filter(Boolean).join(' · ')],
    ['日期', p.published],
    ['引用', p.citations != null ? String(p.citations) : ''],
    ['DOI', p.doi ? `<a href="https://doi.org/${esc(p.doi)}" target="_blank" rel="noopener">${esc(p.doi)}</a>` : ''],
    ['arXiv', p.arxiv_id ? `<a href="https://arxiv.org/abs/${esc(p.arxiv_id)}" target="_blank" rel="noopener">${esc(p.arxiv_id)}</a>` : ''],
  ].filter(r => r[1]);
  box.innerHTML = `<div class="info">
    <h1>${esc(p.title)}</h1>
    <dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${k === 'DOI' || k === 'arXiv' ? v : esc(v)}</dd>`).join('')}</dl>
    ${s.tldr ? `<div class="notice" style="margin-bottom:18px">${icon('sparkles', 16)}<div><b>${esc(s.tldr)}</b>${s.points && s.points.length ? `<ul class="pc-points" style="margin-top:6px">${s.points.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}</div></div>` : ''}
    ${p.s2_tldr ? `<div class="field-label">Semantic Scholar TL;DR</div><p class="abs-block">${esc(p.s2_tldr)}</p>` : ''}
    <div class="field-label">摘要</div>
    <p class="abs-block">${esc(p.abstract || '（无摘要）')}</p>
    <div class="field-label">在其他平台查看</div>
    <div class="row-flex wrap">
      <a class="btn btn-sm" href="${esc(p.url)}" target="_blank" rel="noopener">原文页面</a>
      <a class="btn btn-sm" href="${L.scholar}" target="_blank" rel="noopener">Google Scholar</a>
      <a class="btn btn-sm" href="${L.researchgate}" target="_blank" rel="noopener">ResearchGate</a>
      <a class="btn btn-sm" href="${L.ieee}" target="_blank" rel="noopener">IEEE Xplore</a>
      <a class="btn btn-sm" href="${L.semantic}" target="_blank" rel="noopener">Semantic Scholar</a>
    </div>
  </div>`;
  renderMath(box);
}

// ---------- 选中文字 → 问 AI ----------
let selBar = null;
function hideSelBar() { if (selBar) { selBar.remove(); selBar = null; } }
function onSelect() {
  const sel = window.getSelection();
  const text = sel ? sel.toString().trim() : '';
  hideSelBar();
  if (!text || text.length < 2 || !R) return;
  const rect = sel.getRangeAt(0).getBoundingClientRect();
  selBar = h(`<div class="sel-bar">
    <button data-a="explain">${icon('sparkles', 14)}解释</button>
    <button data-a="translate">${icon('translate', 14)}翻译</button>
    <button data-a="ask">${icon('message', 14)}提问</button>
  </div>`);
  document.body.appendChild(selBar);
  const w = selBar.offsetWidth;
  selBar.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, rect.left + rect.width / 2 - w / 2)) + 'px';
  selBar.style.top = Math.max(8, rect.top - 46) + 'px';
  selBar.onmousedown = e => e.preventDefault();
  selBar.onclick = e => {
    const a = e.target.closest('[data-a]')?.dataset.a;
    if (!a) return;
    hideSelBar();
    document.body.classList.remove('ai-collapsed');
    setAiTab('chat');
    if (a === 'explain') sendChat('请解释这段内容：它在说什么、在论文中起什么作用？涉及的公式或术语也一并说明。', text);
    else if (a === 'translate') sendChat('请把这段内容准确翻译成中文，并解释其中的关键术语。', text);
    else { R.selection = text; renderComposerQuote(); $('[data-input]')?.focus(); }
  };
}

// ---------- 右侧 AI 面板 ----------
function setAiTab(k) {
  if (!R) return;
  R.aiTab = k;
  $$('[data-aitab] button').forEach(b => b.classList.toggle('active', b.dataset.k === k));
  const box = $('[data-ai]');
  box.onscroll = null;
  if (k === 'chat') return renderChat(box);
  if (k === 'related') return renderRelated(box);
  return renderAnalysisTab(box);
}

function renderAnalysisTab(box) {
  if (R.analysis) return renderAnalysis(box, R.analysis);
  box.innerHTML = `<div class="ai-body"><div class="ai-hero">
    <div class="ico-badge">${icon('sparkles', 24)}</div>
    <h3>AI 精读这篇论文</h3>
    <p>读取论文全文，梳理架构脉络与论证主线，<br>拆解方法与实验，标出值得重点关注的地方。</p>
    <button class="btn btn-primary btn-lg" data-go>${icon('sparkles', 16)}生成解读</button>
    ${hasAI() ? '' : '<p class="muted" style="font-size:12.5px;margin:14px 0 0">需要站长密码，或在「AI 设置」里填写你自己的 API</p>'}
  </div><div data-err></div></div>`;
  $('[data-go]', box).onclick = () => {
    if (!hasAI()) { openAiAccess(() => runAnalyze(box, false)); return; }
    runAnalyze(box, false);
  };
}

async function runAnalyze(box, force) {
  const id = R.id;
  const steps = ['正在获取论文全文…', '正在梳理章节结构与论证主线…', '正在拆解方法与实验…', '正在标注重点与难点…', '快好了，正在整理输出…'];
  let si = 0;
  box.innerHTML = `<div class="loading" style="padding-top:80px"><div class="spinner"></div><div data-step>${steps[0]}</div><div class="muted" style="font-size:12px">长论文可能需要 1–2 分钟</div></div>`;
  const t = setInterval(() => { si = Math.min(si + 1, steps.length - 1); const s = $('[data-step]', box); if (s) s.textContent = steps[si]; }, 9000);
  try {
    const res = await api.analyze(id, force);
    clearInterval(t);
    if (!R || R.id !== id) return;
    R.analysis = res;
    if (R.aiTab === 'analysis') renderAnalysis(box, res);
  } catch (e) {
    clearInterval(t);
    if (!R || R.id !== id || R.aiTab !== 'analysis') return;
    renderAnalysisTab(box);
    if (e.code === 'need_ai') { openAiAccess(() => runAnalyze(box, false)); return; }
    $('[data-err]', box).innerHTML = `<div class="notice" style="color:var(--danger)">${icon('alert', 16)}<div>${esc(e.message)}<br><a href="#" data-set>检查 AI 设置</a></div></div>`;
    $('[data-set]', box).onclick = ev => { ev.preventDefault(); if (ME.owner && window.openSettings) window.openSettings(); else openAiAccess(); };
  }
}

function renderAnalysis(box, res) {
  const a = res.data || {};
  const arr = x => (Array.isArray(x) ? x : x ? [x] : []);
  const block = (ic, title, inner) => inner ? `<div class="ana-block"><div class="ana-h">${icon(ic, 15)}${title}</div>${inner}</div>` : '';
  const list = xs => arr(xs).length ? `<ul class="ana-list">${arr(xs).map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '';
  const chain = arr(a.logic_chain).map(x => String(x).replace(/\s*→\s*$/, ''));
  const structure = arr(a.structure);
  const method = a.method || {};
  const exp = a.experiments || {};
  const srcName = { 'arxiv-html': '全文', pdf: '全文', abstract: '摘要' }[res.source] || res.source;
  const when = res.created ? new Date(res.created * 1000).toLocaleString('zh-CN', { hour12: false }) : '';

  box.innerHTML = `<div class="ai-body">
    <div class="ana-one">${esc(a.one_line || '')}</div>
    <div class="row-flex wrap" style="margin-top:10px">
      ${a.difficulty ? `<span class="tag tag-blue">难度 · ${esc(a.difficulty)}</span>` : ''}
      ${arr(a.tags).map(t => `<span class="tag">${esc(t)}</span>`).join('')}
    </div>
    ${block('route', '论证主线', chain.length ? `<div class="chain">${chain.map((c, i) => `<div class="chain-step"><div class="chain-rail"><span class="chain-dot"></span>${i < chain.length - 1 ? '<span class="chain-line"></span>' : ''}</div><div class="chain-text">${esc(c)}</div></div>`).join('')}</div>` : '')}
    ${block('help', '背景与问题', (a.background || a.problem) ? `<p class="ana-p">${esc(a.background || '')}</p>${a.problem ? `<p class="ana-p" style="margin-top:8px"><b>要解决的问题：</b>${esc(a.problem)}</p>` : ''}` : '')}
    ${block('bulb', '主要贡献', list(a.contributions))}
    ${block('tree', '架构脉络 · 点击跳到原文', structure.length ? `<div class="tree">${structure.map((s, i) => `
      <div class="tree-node" data-sec="${i}">
        <div class="tree-sec">${esc(s.section || '')}<span class="go">${icon('chevron', 14)}</span></div>
        ${s.role ? `<div class="tree-role">${esc(s.role)}</div>` : ''}
        ${s.summary ? `<div class="tree-sum">${esc(s.summary)}</div>` : ''}
        ${arr(s.children).length ? `<div class="tree-kids">${arr(s.children).map((c, j) => `<div class="tree-kid" data-kid="${i}-${j}"><b>${esc(c.section || '')}</b>${c.summary ? ' — ' + esc(c.summary) : ''}</div>`).join('')}</div>` : ''}
      </div>`).join('')}</div>` : '')}
    ${block('layers', '方法拆解', (method.overview || arr(method.modules).length) ? `${method.overview ? `<p class="ana-p">${esc(method.overview)}</p>` : ''}
      <div style="margin-top:6px">${arr(method.modules).map(m => `<div class="module"><div class="module-name">${esc(m.name || '')}</div><div class="module-desc">${esc(m.desc || '')}</div>${m.key_formula ? `<div class="module-f">${esc(m.key_formula)}</div>` : ''}</div>`).join('')}</div>` : '')}
    ${block('flask', '实验与结论', (exp.setup || arr(exp.findings).length) ? `${exp.setup ? `<p class="ana-p">${esc(exp.setup)}</p>` : ''}${list(exp.findings)}` : '')}
    ${block('target', '重点关注', arr(a.focus).length ? arr(a.focus).map((f, i) => `<div class="focus-card"><div class="focus-point">${esc(f.point || '')}</div>
        ${f.why ? `<div class="focus-why">${esc(f.why)}</div>` : ''}
        ${f.where ? `<div class="focus-where" data-where="${i}">${icon('file', 13)}${esc(f.where)}</div>` : ''}</div>`).join('') : '')}
    ${block('alert', '局限与可质疑之处', list(a.limitations))}
    ${block('sparkles', '可延伸的方向', list(a.future))}
    ${block('book', '关键术语', arr(a.terms).length ? `<dl class="terms">${arr(a.terms).map(t => `<dt>${esc(t.term || '')}</dt><dd>${esc(t.explain || '')}</dd>`).join('')}</dl>` : '')}
    ${block('layers', '前置知识', list(a.prerequisites))}
    ${block('clock', '阅读建议', a.reading_guide ? `<p class="ana-p">${esc(a.reading_guide)}</p>` : '')}
    <div class="ana-foot"><span>基于${esc(srcName)}生成${res.model ? ' · ' + esc(res.model) : ''}${when ? ' · ' + esc(when) : ''}</span>
      <button class="btn btn-sm btn-ghost" data-ask style="margin-left:auto">${icon('message', 14)}继续追问</button>
      ${ME.owner ? `<button class="btn btn-sm" data-redo>${icon('refresh', 14)}重新生成</button>` : ''}</div>
  </div>`;
  renderMath(box);
  $$('[data-sec]', box).forEach(n => n.addEventListener('click', e => {
    if (e.target.closest('[data-kid]')) return;
    jumpToSection(structure[+n.dataset.sec].section);
  }));
  $$('[data-kid]', box).forEach(n => n.onclick = () => {
    const [i, j] = n.dataset.kid.split('-').map(Number);
    jumpToSection(arr(structure[i].children)[j].section);
  });
  $$('[data-where]', box).forEach(n => n.onclick = () => jumpToSection(arr(a.focus)[+n.dataset.where].where));
  const redo = $('[data-redo]', box);
  if (redo) redo.onclick = async () => {
    if (await confirmDialog('重新生成解读', '将重新调用 AI 生成解读并覆盖当前结果。', { okLabel: '重新生成' })) runAnalyze(box, true);
  };
  $('[data-ask]', box).onclick = () => setAiTab('chat');
}

// ---------- 伴读对话 ----------
function msgEl(m) {
  if (m.role === 'user') {
    let content = m.content;
    let quote = '';
    const mm = content.match(/^我选中了原文中的这段内容：\n> ([\s\S]*?)\n\n([\s\S]*)$/);
    if (mm) { quote = mm[1]; content = mm[2]; }
    return h(`<div class="msg msg-user">${quote ? `<blockquote>${esc(quote)}</blockquote>` : ''}${esc(content)}</div>`);
  }
  const el = h(`<div class="msg msg-ai"><div class="md">${md(m.content)}</div>
    <div class="msg-tools"><button class="icon-btn" data-copy title="复制">${icon('copy', 14)}</button></div></div>`);
  $('[data-copy]', el).onclick = () => navigator.clipboard.writeText(m.content).then(() => toast('已复制'));
  return el;
}

function renderChat(box) {
  box.innerHTML = '';
  const el = h(`<div class="chat">
    <div class="chat-list" data-list></div>
    <div class="quick" data-quick>${QUICK.map(q => `<button class="chip">${esc(q)}</button>`).join('')}</div>
    <div class="composer">
      <div data-quote></div>
      <textarea data-input rows="1" placeholder="向 AI 提问这篇论文…"></textarea>
      <div class="composer-row">
        <button class="btn btn-sm btn-ghost" data-aiset style="height:24px;padding:0 8px;font-size:11.5px" title="AI 设置">${icon('sparkles', 12)}${esc(hasAI() ? aiLabel().text : '开启 AI')}</button>
        <span class="muted" style="font-size:11.5px">Enter 发送</span>
        <button class="icon-btn" data-clear title="清空对话" style="margin-left:auto">${icon('trash', 15)}</button>
        <button class="send" data-send title="发送">${icon('send', 16)}</button>
      </div>
    </div>
  </div>`);
  box.appendChild(el);
  const list = $('[data-list]', el);
  if (!R.chat.length) {
    list.innerHTML = `<div class="ai-hero" style="padding-top:20px"><div class="ico-badge">${icon('message', 24)}</div>
      <h3>边读边问</h3><p>AI 已读过这篇论文的全文。可以问任何细节，<br>也可以在左侧选中一段原文，让 AI 解释或翻译。</p></div>`;
  } else {
    R.chat.forEach(m => list.appendChild(msgEl(m)));
    renderMath(list);
  }
  list.scrollTop = list.scrollHeight;
  $('[data-aiset]', el).onclick = () => openAiAccess(() => renderChat(box));
  $$('[data-quick] .chip', el).forEach(c => c.onclick = () => sendChat(c.textContent));
  const input = $('[data-input]', el);
  const autoGrow = () => { input.style.height = 'auto'; input.style.height = Math.min(160, input.scrollHeight) + 'px'; };
  input.oninput = autoGrow;
  input.onkeydown = e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('[data-send]', el).click(); }
  };
  $('[data-send]', el).onclick = () => {
    const q = input.value.trim();
    if (!q) return;
    input.value = '';
    autoGrow();
    sendChat(q);
  };
  $('[data-clear]', el).onclick = async () => {
    if (!R.chat.length) return;
    if (!await confirmDialog('清空对话', '将删除与这篇论文的全部对话记录。', { okLabel: '清空', danger: true })) return;
    await api.chatClear(R.id);
    R.chat = [];
    renderChat(box);
  };
  renderComposerQuote();
  updateSendState();
}

function renderComposerQuote() {
  const q = $('[data-quote]');
  if (!q) return;
  q.innerHTML = R.selection ? `<div class="sel-quote"><span>“${esc(R.selection)}”</span><button class="icon-btn" style="width:22px;height:22px" data-unq>${icon('x', 12)}</button></div>` : '';
  const b = $('[data-unq]', q);
  if (b) b.onclick = () => { R.selection = null; renderComposerQuote(); };
}

function updateSendState() {
  const b = $('[data-send]');
  if (b) b.disabled = !!(R && R.sending);
}

async function sendChat(question, selection) {
  if (!R || R.sending) return;
  if (!hasAI()) { openAiAccess(() => sendChat(question, selection)); return; }
  if (R.aiTab !== 'chat') setAiTab('chat');
  const sel = selection || R.selection || null;
  R.selection = null;
  renderComposerQuote();
  const list = $('[data-list]');
  if (!R.chat.length) list.innerHTML = '';
  const userContent = sel ? `我选中了原文中的这段内容：\n> ${sel}\n\n${question}` : question;
  R.chat.push({ role: 'user', content: userContent });
  list.appendChild(msgEl({ role: 'user', content: userContent }));
  const aiEl = h(`<div class="msg msg-ai"><div class="md"><div class="muted" data-st style="font-size:12.5px"></div><span class="typing"><i></i><i></i><i></i></span></div></div>`);
  list.appendChild(aiEl);
  list.scrollTop = list.scrollHeight;
  R.sending = true;
  updateSendState();
  const id = R.id;
  const ctrl = new AbortController();
  R.abort = ctrl;
  let text = '';
  let raf = 0;
  const paint = () => {
    raf = 0;
    const mdEl = $('.md', aiEl);
    const stick = list.scrollHeight - list.scrollTop - list.clientHeight < 60;
    mdEl.innerHTML = md(text);
    if (stick) list.scrollTop = list.scrollHeight;
  };
  try {
    await chatStream({ id, message: question, selection: sel }, ev => {
      if (ev.type === 'status') { const s = $('[data-st]', aiEl); if (s) s.textContent = ev.text; }
      else if (ev.type === 'start') { const s = $('[data-st]', aiEl); if (s) s.textContent = ev.source === 'abstract' ? '（未获取到全文，基于摘要回答）' : ''; }
      else if (ev.type === 'delta') { text += ev.text; if (!raf) raf = requestAnimationFrame(paint); }
      else if (ev.type === 'error') throw new Error(ev.text);
    }, ctrl.signal);
    if (raf) cancelAnimationFrame(raf);
    if (!R || R.id !== id) return;
    R.chat.push({ role: 'assistant', content: text });
    aiEl.replaceWith(msgEl({ role: 'assistant', content: text }));
    renderMath(list.lastElementChild);
    list.scrollTop = list.scrollHeight;
  } catch (e) {
    if (e.name === 'AbortError') return;
    if (!R || R.id !== id) return;
    if (e.code === 'need_ai') {
      R.chat.pop();
      const prev = aiEl.previousElementSibling;
      if (prev) prev.remove();
      aiEl.remove();
      openAiAccess(() => sendChat(question, sel));
      return;
    }
    aiEl.classList.add('err');
    aiEl.innerHTML = `<div class="md">${text ? md(text) + '<hr>' : ''}${icon('alert', 14)} ${esc(e.message)}</div>`;
  } finally {
    if (R && R.id === id) { R.sending = false; R.abort = null; updateSendState(); }
  }
}

// ---------- 相关论文 ----------
async function renderRelated(box) {
  const id = R.id;
  if (!R.similar) {
    box.innerHTML = `<div class="loading" style="padding-top:60px"><div class="spinner"></div>正在从 Semantic Scholar、OpenAlex、arXiv 现场查找相关论文…</div>`;
    try {
      R.similar = await api.similar(id);
    } catch (e) {
      if (R && R.id === id && R.aiTab === 'related') box.innerHTML = emptyState('alert', esc(e.message));
      return;
    }
  }
  if (!R || R.id !== id || R.aiTab !== 'related') return;
  const { web, keyword, phrases } = R.similar;
  const mini = (p, meta) => `<div class="mini" data-id="${esc(p.id)}"><div class="mini-title">${esc(p.title)}</div>
    <div class="mini-meta">${esc([p.source, (p.published || '').slice(0, 4), meta].filter(Boolean).join(' · '))}${p._fav ? ' · ★' : ''}</div></div>`;
  box.innerHTML = `<div class="ai-body" style="padding:12px 8px 24px">
    <div class="ana-h" style="padding:6px 14px 0">${icon('globe', 15)}全网相关${web.provider ? ` · ${esc(web.provider)}` : ''}</div>
    ${web.items.length ? web.items.map(p => mini(p, p.citations ? `引用 ${p.citations}` : '')).join('') : `<div class="muted" style="padding:8px 14px 4px;font-size:13px">${web.errors && web.errors.length ? '外部推荐接口暂时不可用（可能被限流），稍后再试' : '没有找到'}</div>`}
    <div class="ana-h" style="padding:18px 14px 0">${icon('search', 15)}同主题论文${phrases && phrases.length ? ` · ${esc(phrases.join(' / '))}` : ''}</div>
    ${keyword.length ? keyword.map(x => mini(x.paper, `相似度 ${(x.score * 100).toFixed(0)}%`)).join('') : '<div class="muted" style="padding:8px 14px;font-size:13px">没有找到同主题的论文</div>'}
    <div style="padding:14px"><button class="btn btn-sm" data-reload>${icon('refresh', 14)}刷新</button></div>
  </div>`;
  $$('.mini', box).forEach(m => m.onclick = () => { location.hash = paperUrl(m.dataset.id); });
  $('[data-reload]', box).onclick = () => { R.similar = null; renderRelated(box); };
}

// ---------- 外部链接菜单 ----------
let menuEl = null;
function closeMenu() { if (menuEl) { menuEl.remove(); menuEl = null; document.removeEventListener('mousedown', onDocDown, true); } }
function onDocDown(e) { if (menuEl && !menuEl.contains(e.target)) closeMenu(); }
function openMoreMenu(anchor) {
  if (menuEl) { closeMenu(); return; }
  const p = R.paper;
  const L = externalLinks(p);
  const items = [
    ['external', '原文页面', p.url],
    R.pdfUrl ? ['file', '在新窗口打开 PDF', `/api/pdf?id=${encodeURIComponent(p.id)}`] : null,
    null,
    ['globe', 'Google Scholar', L.scholar],
    ['globe', 'ResearchGate', L.researchgate],
    ['globe', 'IEEE Xplore', L.ieee],
    ['globe', 'Semantic Scholar', L.semantic],
    null,
    ['download', '导出 BibTeX', `/api/export/bibtex?ids=${encodeURIComponent(p.id)}`],
  ];
  menuEl = h(`<div class="popover menu"></div>`);
  let last = null;
  for (const it of items) {
    if (!it) { if (last) menuEl.appendChild(h('<div class="menu-sep"></div>')); last = null; continue; }
    const row = h(`<div class="menu-item"><span class="menu-icon">${icon(it[0], 15)}</span><span class="menu-label">${esc(it[1])}</span></div>`);
    row.onclick = () => { window.open(it[2], '_blank', 'noopener'); closeMenu(); };
    menuEl.appendChild(row);
    last = row;
  }
  document.body.appendChild(menuEl);
  const r = anchor.getBoundingClientRect();
  menuEl.style.top = r.bottom + 6 + 'px';
  menuEl.style.left = Math.min(window.innerWidth - menuEl.offsetWidth - 8, r.right - menuEl.offsetWidth) + 'px';
  menuEl.style.transformOrigin = 'top right';
  setTimeout(() => document.addEventListener('mousedown', onDocDown, true), 0);
}

// ---------- 拖动调整 AI 面板宽度 ----------
function setupResizer(handle) {
  handle.addEventListener('mousedown', e => {
    e.preventDefault();
    handle.classList.add('drag');
    const frame = $('.pdf-frame');
    if (frame) frame.style.pointerEvents = 'none';
    const move = ev => {
      const w = Math.max(320, Math.min(window.innerWidth * 0.6, window.innerWidth - ev.clientX - 12));
      document.documentElement.style.setProperty('--ai-w', w + 'px');
    };
    const up = () => {
      handle.classList.remove('drag');
      if (frame) frame.style.pointerEvents = '';
      document.removeEventListener('mousemove', move);
      document.removeEventListener('mouseup', up);
      try { localStorage.setItem('aiWidth', parseInt(getComputedStyle(document.documentElement).getPropertyValue('--ai-w'), 10)); } catch (err) { /* ignore */ }
    };
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up);
  });
}
