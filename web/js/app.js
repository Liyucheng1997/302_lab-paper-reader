// 入口：路由、侧栏、发现 / 检索 / 收藏 / 历史 / 设置
import { ME, aiLabel, openAiAccess, refreshMe } from './access.js';
import { api } from './api.js';
import { openLook } from './look.js';
import { openFavorite } from './favorite.js';
import { renderReader, leaveReader } from './reader.js';
import {
  $, $$, confirmDialog, dayLabel, emptyState, engineName, esc, externalLinks, fmtDuration, fmtTime, h, icon,
  modal, paperCard, paperUrl, promptDialog, skeletons, toast,
} from './ui.js';

export const S = {
  meta: null,
  feedField: '',
  feedSource: '',
  feedOnlySum: false,
  search: { q: '', sources: null, sort: 'relevance', year: '' },
  lib: { folder: 'all', status: '', tag: '', q: '' },
};

const view = () => document.getElementById('view');

// ---------- 主题 ----------
function setTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  try { localStorage.setItem('theme', t); } catch (e) { /* ignore */ }
  renderSidebar();
}

// ---------- 侧栏 ----------
function renderSidebar() {
  const route = (location.hash.split('?')[0] || '#/').slice(1) || '/';
  const isOn = r => (r === '/' ? route === '/' : route.startsWith(r)) ? 'active' : '';
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  const lab = aiLabel();
  const sb = document.getElementById('sidebar');
  sb.innerHTML = `
    <div class="brand"><div class="logo-mark">文</div><div class="brand-text"><div class="brand-name">论文阅读</div><div class="brand-sub">Paper Reader · AI</div></div></div>
    <a class="nav-item ${isOn('/')}" href="#/">${icon('compass')}<span class="nav-label">发现</span></a>
    <a class="nav-item ${isOn('/search')}" href="#/search">${icon('search')}<span class="nav-label">检索</span></a>
    <div class="nav-group">我的</div>
    <a class="nav-item ${isOn('/library')}" href="#/library">${icon('bookmark')}<span class="nav-label">收藏夹</span></a>
    <a class="nav-item ${isOn('/history')}" href="#/history">${icon('clock')}<span class="nav-label">阅读记录</span></a>
    <div class="sidebar-bottom">
      <button class="nav-item opt" data-look title="外观：纸张颜色、字号、深浅色">${icon('palette')}<span class="nav-label">外观</span></button>
      <button class="nav-item" data-nav-ai title="AI 设置：${esc(lab.text)}">${icon('sparkles')}<span class="nav-label">AI 设置</span><span class="count ${lab.cls === 'ok' ? 'ai-on' : ''}">${ME.owner ? '站长' : lab.cls === 'ok' ? '自有' : '未开启'}</span></button>
      ${ME.owner ? `<button class="nav-item" data-settings title="服务器设置">${icon('sliders')}<span class="nav-label">设置</span></button>` : ''}
    </div>`;
  $('[data-look]', sb).onclick = e => openLook(e.currentTarget, 'right');
  $('[data-nav-ai]', sb).onclick = () => openAiAccess();
  const st = $('[data-settings]', sb);
  if (st) st.onclick = openSettings;
}

// ---------- 路由 ----------
function parseHash() {
  const raw = location.hash.slice(1) || '/';
  const [path, query] = raw.split('?');
  return { path, params: new URLSearchParams(query || '') };
}

async function route() {
  const { path, params } = parseHash();
  renderSidebar();
  const isReader = path.startsWith('/paper/');
  document.body.classList.toggle('reader-mode', isReader);
  if (!isReader) leaveReader();
  view().scrollTop = 0;
  try {
    if (isReader) return await renderReader(view(), decodeURIComponent(path.slice(7)));
    if (path === '/search') return await renderSearch(params);
    if (path === '/library') return await renderLibrary();
    if (path === '/history') return await renderHistory();
    return await renderDiscover();
  } catch (e) {
    view().innerHTML = `<div class="page">${emptyState('alert', esc(e.message))}</div>`;
  }
}

// 收藏后刷新卡片上的星标
export function favHandler(after) {
  return (p, el) => openFavorite(p, fav => {
    p._fav = !!fav;
    const btn = el && $('[data-act="fav"]', el);
    if (btn) { btn.classList.toggle('fav-on', !!fav); $('.pc-actions', el).classList.toggle('show', !!fav); }
    after && after(fav);
  });
}

// ---------- 发现 ----------
function greeting() {
  const hr = new Date().getHours();
  if (hr < 6) return '夜深了';
  if (hr < 11) return '早上好';
  if (hr < 14) return '中午好';
  if (hr < 18) return '下午好';
  return '晚上好';
}

async function renderDiscover() {
  if (!S.meta) S.meta = await api.meta();
  const meta = S.meta;
  const fieldChips = [['', '全部', meta.feed_total], ...Object.entries(meta.fields).map(([k, v]) => [k, v.name, v.count])];
  const page = h(`<div class="page">
    <section class="hero">
      <div class="hero-hello">${greeting()} 👋</div>
      <h1 class="hero-title">今天想读点<em>什么</em>？</h1>
      <form class="search-pill" data-search>
        ${icon('search', 20)}
        <input name="q" placeholder="检索 arXiv、IEEE、Semantic Scholar、OpenAlex、Google Scholar 上的论文" autocomplete="off">
        <span class="kbd">/</span>
        <button class="btn btn-primary btn-lg" type="submit">检索</button>
      </form>
      <div class="interest" data-interest></div>
    </section>

    <section class="section">
      <div class="section-head">
        <div><div class="eyebrow">For you</div><h2 class="section-title">为你推荐</h2></div>
        <div class="row-flex"><span class="muted" data-recmeta style="font-size:12.5px"></span>
          <button class="btn btn-sm" data-recrefresh title="按你的兴趣当场重新检索">${icon('refresh', 14)}换一批</button></div>
      </div>
      <div data-rec>${skeletons(3)}</div>
    </section>

    <section class="section">
      <div class="section-head">
        <div><div class="eyebrow">Latest</div><h2 class="section-title">最新论文</h2></div>
        <div class="row-flex">
          <span class="muted" style="font-size:12.5px">${meta.feed_updated ? '更新于 ' + esc(meta.feed_updated) : ''}</span>
          ${ME.owner ? `<select class="input" data-upaction style="height:32px;width:auto">
            <option value="all">抓取 + 总结</option><option value="fetch">仅抓取</option><option value="summarize">仅总结</option>
          </select>
          <button class="btn" data-update>${icon('refresh', 15)}更新</button>` : ''}
        </div>
      </div>
      <div data-uppanel class="hidden"><div class="row-flex"><span class="state blue" data-uptitle>正在更新…</span><button class="icon-btn" data-upclose style="margin-left:auto">${icon('x', 14)}</button></div><pre class="update-log" data-uplog></pre></div>
      <div class="toolbar">
        <div class="chips" data-fields>${fieldChips.map(([k, n, c]) => `<button class="chip ${S.feedField === k ? 'active' : ''}" data-k="${k}">${esc(n)}<span class="n">${c}</span></button>`).join('')}</div>
      </div>
      <div class="toolbar">
        <div class="seg" data-src>${[['', '全部来源'], ['arXiv', 'arXiv'], ['IEEE', 'IEEE'], ['期刊', '其他期刊']].map(([k, n]) => `<button data-k="${k}" class="${S.feedSource === k ? 'active' : ''}">${n}</button>`).join('')}</div>
        <label class="check"><input type="checkbox" data-onlysum ${S.feedOnlySum ? 'checked' : ''}>仅看已有 AI 总结</label>
        <span class="muted" data-count style="margin-left:auto;font-size:13px"></span>
      </div>
      <div data-feed>${skeletons(4)}</div>
    </section>
  </div>`);
  view().replaceChildren(page);

  $('[data-search]', page).onsubmit = e => {
    e.preventDefault();
    const q = e.target.q.value.trim();
    if (q) location.hash = '#/search?q=' + encodeURIComponent(q);
  };

  // 推荐
  const recBox = $('[data-rec]', page);
  const recMeta = $('[data-recmeta]', page);
  const SRC_STATE = { ok: '', 限流: '限流', 失败: '失败', 超时: '超时' };
  const loadRec = async (refresh = false) => {
    recBox.innerHTML = `<div class="loading" style="padding:28px 0"><div class="spinner"></div>${refresh ? '正在按你的兴趣，从 arXiv、OpenAlex、Semantic Scholar 现场挑选…' : '正在准备推荐…'}</div>`;
    const btn = $('[data-recrefresh]', page);
    btn.disabled = true;
    try {
      const r = await api.recommend(refresh ? { refresh: 1 } : {});
      const kw = $('[data-interest]', page);
      kw.innerHTML = r.keywords.length
        ? `<span class="interest-label">你的兴趣画像</span>` + r.keywords.slice(0, 12).map(k => `<button class="chip chip-sm" data-q="${esc(k)}">${esc(k)}</button>`).join('')
        : '';
      $$('[data-q]', kw).forEach(b => b.onclick = () => { location.hash = '#/search?q=' + encodeURIComponent(b.dataset.q); });
      const mins = Math.max(0, Math.round((Date.now() / 1000 - r.created) / 60));
      const srcs = Object.entries(r.sources || {}).map(([k, v]) => k + (SRC_STATE[v] ? `（${SRC_STATE[v]}）` : '')).join(' · ');
      recMeta.textContent = r.cold_start ? '读几篇论文后会按你的兴趣现场推荐'
        : `${mins < 1 ? '刚刚' : mins < 60 ? mins + ' 分钟前' : Math.round(mins / 60) + ' 小时前'}从 ${r.candidates || 0} 篇候选中挑选${srcs ? ' · ' + srcs : ''}`;
      if (!r.items.length) { recBox.innerHTML = emptyState('sparkles', '这次没有找到合适的新论文，点「换一批」再试试'); return; }
      const grid = h('<div class="pgrid"></div>');
      for (const it of r.items) {
        const rs = it.reason || {};
        let reason = '';
        if (r.cold_start) reason = '最新论文 · 读几篇后推荐会更懂你';
        else if (rs.similar_to) reason = `因为你读过 <b>${esc(rs.similar_to.title.slice(0, 48))}${rs.similar_to.title.length > 48 ? '…' : ''}</b>`;
        else if (rs.terms && rs.terms.length) reason = `匹配你的兴趣：<b>${rs.terms.map(esc).join('、')}</b>`;
        grid.appendChild(paperCard(it.paper, {
          compact: true, dismiss: !r.cold_start, onFav: favHandler(),
          extra: reason ? `<div class="reason">${reason}</div>` : '',
          onDismiss: async (p, el) => {
            await api.dismiss(p.id).catch(() => {});
            el.style.transition = 'opacity .25s, transform .25s';
            el.style.opacity = '0'; el.style.transform = 'scale(.96)';
            setTimeout(() => el.remove(), 250);
            toast('已减少此类推荐');
          },
        }));
      }
      recBox.replaceChildren(grid);
    } catch (e) {
      recBox.innerHTML = emptyState('alert', esc(e.message));
    } finally {
      btn.disabled = false;
    }
  };
  $('[data-recrefresh]', page).onclick = () => loadRec(true);
  loadRec();

  // 订阅论文流
  let feed = [];
  const feedBox = $('[data-feed]', page);
  const renderFeed = () => {
    const list = feed.filter(p => (!S.feedField || p.field === S.feedField)
      && (!S.feedSource || p.source === S.feedSource) && (!S.feedOnlySum || p.summary));
    $('[data-count]', page).textContent = `共 ${list.length} 篇`;
    if (!list.length) { feedBox.innerHTML = emptyState('book', '没有符合条件的论文'); return; }
    const box = h('<div class="plist"></div>');
    list.slice(0, 120).forEach(p => box.appendChild(paperCard(p, { points: true, onFav: favHandler() })));
    feedBox.replaceChildren(box);
  };
  $$('[data-fields] .chip', page).forEach(b => b.onclick = () => {
    S.feedField = b.dataset.k;
    $$('[data-fields] .chip', page).forEach(x => x.classList.toggle('active', x === b));
    renderFeed();
  });
  $$('[data-src] button', page).forEach(b => b.onclick = () => {
    S.feedSource = b.dataset.k;
    $$('[data-src] button', page).forEach(x => x.classList.toggle('active', x === b));
    renderFeed();
  });
  $('[data-onlysum]', page).onchange = e => { S.feedOnlySum = e.target.checked; renderFeed(); };
  api.feed().then(r => { feed = r.papers; renderFeed(); }).catch(e => { feedBox.innerHTML = emptyState('alert', esc(e.message)); });

  if (ME.owner) setupUpdater(page);
}

// ---------- 订阅更新（抓取 + 总结） ----------
let pollTimer = null;
function setupUpdater(page) {
  const panel = $('[data-uppanel]', page);
  const log = $('[data-uplog]', page);
  const title = $('[data-uptitle]', page);
  const btn = $('[data-update]', page);
  const NAMES = { all: '抓取 + 总结', fetch: '抓取论文', summarize: '生成总结' };
  const poll = async () => {
    if (!document.body.contains(page)) { clearInterval(pollTimer); pollTimer = null; return; }
    let st;
    try { st = await api.status(); } catch (e) { return; }
    if (st.log?.length || st.running) panel.classList.remove('hidden');
    const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 30;
    log.textContent = (st.log || []).join('\n');
    if (atBottom) log.scrollTop = log.scrollHeight;
    if (st.running) {
      btn.disabled = true;
      title.className = 'state blue';
      title.textContent = `正在${NAMES[st.action] || '更新'}…（可离开页面，任务在后台继续）`;
      if (!pollTimer) pollTimer = setInterval(poll, 2000);
    } else {
      btn.disabled = false;
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
      if (st.exit_code === null) panel.classList.add('hidden');
      else {
        title.className = st.exit_code === 0 ? 'state ok' : 'state err';
        title.textContent = st.exit_code === 0 ? '更新完成' : '更新失败，详见日志';
      }
    }
    return st;
  };
  btn.onclick = async () => {
    try {
      await api.update($('[data-upaction]', page).value);
      panel.classList.remove('hidden');
      if (!pollTimer) pollTimer = setInterval(async () => {
        const st = await poll();
        if (st && !st.running && st.exit_code === 0) { S.meta = null; toast('论文库已更新', 'success'); route(); }
      }, 2000);
      poll();
    } catch (e) { toast(e.message, 'error'); }
  };
  $('[data-upclose]', page).onclick = () => panel.classList.add('hidden');
  poll();
}

// ---------- 检索 ----------
async function renderSearch(params) {
  if (!S.meta) S.meta = await api.meta();
  const engines = S.meta.engines;
  const q = params.get('q') || '';
  if (!S.search.sources) S.search.sources = new Set(S.meta.default_sources || engines.filter(e => !e.link_only).map(e => e.key));
  S.search.q = q;
  const page = h(`<div class="page">
    <div class="page-head"><div><div class="eyebrow">Search</div><h1 class="page-title">多源学术检索</h1>
      <p class="page-desc">同时检索多个学术数据库，自动去重合并，并按各库排名融合排序。</p></div></div>
    <form class="search-top" data-form>
      <div class="search-pill">${icon('search', 20)}<input name="q" placeholder="关键词、标题、作者… 支持 arXiv 语法如 ti:transformer" value="${esc(q)}" autocomplete="off"></div>
      <button class="btn btn-primary btn-lg" type="submit">检索</button>
    </form>
    <div class="toolbar" style="margin-top:16px">
      <div class="chips" data-engines></div>
    </div>
    <div class="toolbar">
      <div class="seg" data-sort>${[['relevance', '相关度'], ['date', '最新发表'], ['citations', '引用数']].map(([k, n]) => `<button data-k="${k}">${n}</button>`).join('')}</div>
      <select class="input" data-year style="height:32px;width:auto">
        <option value="">不限年份</option>${[2026, 2025, 2024, 2023, 2022, 2020, 2018, 2015].map(y => `<option value="${y}">${y} 年至今</option>`).join('')}
      </select>
    </div>
    <div data-status class="src-status"></div>
    <div data-results></div>
  </div>`);
  view().replaceChildren(page);
  $('[data-year]', page).value = S.search.year;

  const engBox = $('[data-engines]', page);
  const renderEngines = () => {
    engBox.innerHTML = engines.map(e => {
      if (e.link_only) return `<button class="chip off" data-link="${e.key}" title="${esc(e.hint)}">${esc(e.name)}${icon('external', 13)}</button>`;
      const on = S.search.sources.has(e.key);
      return `<button class="chip ${on && e.configured ? 'active' : ''} ${e.configured ? '' : 'off'}" data-eng="${e.key}" title="${esc(e.configured ? '' : e.hint)}">${esc(e.name)}${e.configured ? '' : '<span class="n">需配置</span>'}</button>`;
    }).join('');
    $$('[data-eng]', engBox).forEach(b => b.onclick = () => {
      const e = engines.find(x => x.key === b.dataset.eng);
      if (!e.configured) { toast(e.hint); openSettings(); return; }
      S.search.sources.has(e.key) ? S.search.sources.delete(e.key) : S.search.sources.add(e.key);
      renderEngines();
    });
    $$('[data-link]', engBox).forEach(b => b.onclick = () => {
      const term = $('input[name=q]', page).value.trim();
      window.open(`https://www.researchgate.net/search/publication?q=${encodeURIComponent(term)}`, '_blank', 'noopener');
    });
  };
  renderEngines();
  const renderSort = () => $$('[data-sort] button', page).forEach(b => b.classList.toggle('active', b.dataset.k === S.search.sort));
  renderSort();
  $$('[data-sort] button', page).forEach(b => b.onclick = () => { S.search.sort = b.dataset.k; renderSort(); run(); });
  $('[data-year]', page).onchange = e => { S.search.year = e.target.value; run(); };
  $('[data-form]', page).onsubmit = e => {
    e.preventDefault();
    const nq = e.target.q.value.trim();
    if (!nq) return;
    if (nq === S.search.q) run();
    else location.hash = '#/search?q=' + encodeURIComponent(nq);
  };

  const resBox = $('[data-results]', page);
  const stBox = $('[data-status]', page);
  async function run() {
    const term = S.search.q;
    if (!term) {
      resBox.innerHTML = emptyState('search', '输入关键词开始检索。<br>没有配置 key 的数据源（IEEE Xplore、Google Scholar）会自动跳过，可在「设置」中开启。');
      return;
    }
    stBox.innerHTML = `<span class="state blue">正在检索 ${[...S.search.sources].map(engineName).join('、')}…</span>`;
    resBox.innerHTML = skeletons(5);
    try {
      const r = await api.search({ q: term, sources: [...S.search.sources].join(','), sort: S.search.sort, year_from: S.search.year, limit: 20 });
      stBox.innerHTML = Object.entries(r.status).map(([k, s]) => {
        if (s.ok) return `<span class="state ok">${engineName(k)} ${s.count} 篇</span>`;
        if (s.skipped) return `<span class="state" title="${esc(s.error)}">${engineName(k)} 未配置</span>`;
        const why = /429/.test(s.error) ? '限流' : '失败';
        return `<span class="state warn" title="${esc(s.error)}">${engineName(k)} ${why}</span>`;
      }).join('') + `<span class="muted" style="font-size:12.5px">合并去重后 ${r.results.length} 篇 · ${r.elapsed}s</span>`;
      const links = externalLinks({ title: term });
      const list = h('<div class="plist"></div>');
      r.results.forEach(p => list.appendChild(paperCard(p, { foundIn: true, onFav: favHandler() })));
      resBox.replaceChildren(list);
      resBox.appendChild(h(`<div class="linkouts" style="margin-top:20px">在其他网站继续检索：
        <a href="${links.scholar}" target="_blank" rel="noopener">Google Scholar</a>
        <a href="${links.researchgate}" target="_blank" rel="noopener">ResearchGate</a>
        <a href="${links.ieee}" target="_blank" rel="noopener">IEEE Xplore</a></div>`));
      if (!r.results.length) resBox.insertAdjacentHTML('afterbegin', emptyState('search', '没有找到相关论文，换个关键词试试'));
    } catch (e) {
      stBox.innerHTML = '';
      resBox.innerHTML = emptyState('alert', esc(e.message));
    }
  }
  run();
  if (!q) $('input[name=q]', page).focus();
}

// ---------- 收藏夹 ----------
async function renderLibrary() {
  const page = h(`<div class="page">
    <div class="page-head">
      <div><div class="eyebrow">Library</div><h1 class="page-title">收藏夹</h1><p class="page-desc">按文件夹、阅读状态和标签整理你收藏的论文。</p></div>
      <a class="btn" data-export>${icon('download', 15)}导出 BibTeX</a>
    </div>
    <div class="lib">
      <nav class="lib-side" data-side></nav>
      <div>
        <div class="toolbar">
          <div class="seg" data-status>${[['', '全部'], ['todo', '待读'], ['reading', '在读'], ['done', '已读']].map(([k, n]) => `<button data-k="${k}">${n}</button>`).join('')}</div>
          <input class="input" data-q placeholder="在收藏中搜索…" style="flex:1;min-width:160px" value="${esc(S.lib.q)}">
        </div>
        <div class="chips" data-tags style="margin-bottom:14px"></div>
        <div data-list>${skeletons(3)}</div>
      </div>
    </div>
  </div>`);
  view().replaceChildren(page);
  let data;
  const load = async () => { data = await api.favorites(); render(); };

  const render = () => {
    const { items, folders, tags } = data;
    const side = $('[data-side]', page);
    const unfiled = items.filter(it => !it.fav.folder_ids.length).length;
    side.innerHTML = `
      <button class="nav-item ${S.lib.folder === 'all' ? 'active' : ''}" data-f="all">${icon('bookmark')}<span class="nav-label">全部收藏</span><span class="count">${items.length}</span></button>
      <button class="nav-item ${S.lib.folder === 'none' ? 'active' : ''}" data-f="none">${icon('layers')}<span class="nav-label">未分类</span><span class="count">${unfiled}</span></button>
      <div class="nav-group">文件夹</div>
      ${folders.map(f => `<div class="folder-item"><button class="nav-item ${String(S.lib.folder) === String(f.id) ? 'active' : ''}" data-f="${f.id}">${icon('folder')}<span class="nav-label" style="overflow:hidden;text-overflow:ellipsis">${esc(f.name)}</span><span class="count">${f.count}</span></button>
        <span class="f-actions"><button class="icon-btn" data-rename="${f.id}" title="重命名">${icon('edit', 14)}</button><button class="icon-btn" data-del="${f.id}" title="删除文件夹">${icon('trash', 14)}</button></span></div>`).join('')}
      <button class="nav-item" data-newf style="color:var(--primary)">${icon('plus')}<span class="nav-label">新建文件夹</span></button>`;
    $$('[data-f]', side).forEach(b => b.onclick = () => { S.lib.folder = b.dataset.f; render(); });
    $('[data-newf]', side).onclick = async () => {
      const name = await promptDialog('新建文件夹', '', '如：车辆动力学、强化学习、组会待讲');
      if (!name) return;
      try { const r = await api.folderCreate(name); S.lib.folder = String(r.id); await load(); } catch (e) { toast(e.message, 'error'); }
    };
    $$('[data-rename]', side).forEach(b => b.onclick = async e => {
      e.stopPropagation();
      const f = folders.find(x => String(x.id) === b.dataset.rename);
      const name = await promptDialog('重命名文件夹', f.name);
      if (!name || name === f.name) return;
      try { await api.folderRename(f.id, name); await load(); } catch (err) { toast(err.message, 'error'); }
    });
    $$('[data-del]', side).forEach(b => b.onclick = async e => {
      e.stopPropagation();
      const f = folders.find(x => String(x.id) === b.dataset.del);
      if (!await confirmDialog('删除文件夹', `删除「${f.name}」？其中的论文仍保留在收藏中（变为未分类）。`, { okLabel: '删除', danger: true })) return;
      await api.folderDelete(f.id);
      if (String(S.lib.folder) === String(f.id)) S.lib.folder = 'all';
      await load();
    });

    $$('[data-status] button', page).forEach(b => {
      b.classList.toggle('active', b.dataset.k === S.lib.status);
      b.onclick = () => { S.lib.status = b.dataset.k; render(); };
    });
    const tagBox = $('[data-tags]', page);
    tagBox.innerHTML = tags.slice(0, 30).map(([t, n]) => `<button class="chip chip-sm ${S.lib.tag === t ? 'active' : ''}" data-t="${esc(t)}">#${esc(t)}<span class="n">${n}</span></button>`).join('');
    $$('[data-t]', tagBox).forEach(b => b.onclick = () => { S.lib.tag = S.lib.tag === b.dataset.t ? '' : b.dataset.t; render(); });

    const exp = $('[data-export]', page);
    exp.href = '/api/export/bibtex' + (/^\d+$/.test(S.lib.folder) ? `?folder=${S.lib.folder}` : '');

    const q = S.lib.q.toLowerCase();
    const list = items.filter(({ fav, paper }) => {
      if (S.lib.folder === 'none' && fav.folder_ids.length) return false;
      if (/^\d+$/.test(S.lib.folder) && !fav.folder_ids.map(String).includes(S.lib.folder)) return false;
      if (S.lib.status && fav.status !== S.lib.status) return false;
      if (S.lib.tag && !fav.tags.includes(S.lib.tag)) return false;
      if (q && !`${paper.title} ${(paper.authors || []).join(' ')} ${fav.note} ${fav.tags.join(' ')} ${paper.venue || ''}`.toLowerCase().includes(q)) return false;
      return true;
    });
    const box = $('[data-list]', page);
    if (!list.length) {
      box.innerHTML = emptyState('bookmark', items.length ? '这里还没有论文' : '还没有收藏。阅读时点星标即可收藏并分类整理。');
      return;
    }
    const plist = h('<div class="plist"></div>');
    const fname = Object.fromEntries(folders.map(f => [f.id, f.name]));
    const SN = { todo: ['待读', ''], reading: ['在读', 'blue'], done: ['已读', 'ok'] };
    for (const { fav, paper } of list) {
      const extra = `<div class="fav-meta">
          <span class="state ${SN[fav.status][1]}">${SN[fav.status][0]}</span>
          ${fav.folder_ids.map(id => `<span class="tag">${icon('folder', 12)}&nbsp;${esc(fname[id] || '')}</span>`).join('')}
          ${fav.tags.map(t => `<span class="tag tag-blue">#${esc(t)}</span>`).join('')}
        </div>${fav.note ? `<div class="fav-note">${esc(fav.note)}</div>` : ''}`;
      plist.appendChild(paperCard(paper, { compact: false, extra, onFav: (p) => openFavorite(p, () => load()) }));
    }
    box.replaceChildren(plist);
  };
  let t;
  $('[data-q]', page).oninput = e => { clearTimeout(t); t = setTimeout(() => { S.lib.q = e.target.value.trim(); render(); }, 150); };
  await load();
}

// ---------- 阅读记录 ----------
async function renderHistory() {
  const [{ items }, favs] = await Promise.all([api.history(), api.favorites()]);
  const total = items.reduce((s, x) => s + (x.seconds || 0), 0);
  const weekAgo = Date.now() / 1000 - 7 * 86400;
  const week = items.filter(x => x.last_read >= weekAgo).length;
  const page = h(`<div class="page">
    <div class="page-head">
      <div><div class="eyebrow">History</div><h1 class="page-title">阅读记录</h1><p class="page-desc">自动记录你打开过的论文和阅读时长，用于个性化推荐。</p></div>
      ${items.length ? `<button class="btn btn-danger" data-clear>${icon('trash', 15)}清空记录</button>` : ''}
    </div>
    <div class="stats">
      <div class="stat"><div class="stat-label">读过的论文</div><div class="stat-num">${items.length}</div><div class="stat-sub">篇</div></div>
      <div class="stat"><div class="stat-label">累计阅读</div><div class="stat-num">${Math.round(total / 60)}</div><div class="stat-sub">分钟</div></div>
      <div class="stat"><div class="stat-label">最近 7 天</div><div class="stat-num">${week}</div><div class="stat-sub">篇</div></div>
      <div class="stat"><div class="stat-label">收藏</div><div class="stat-num">${favs.items.length}</div><div class="stat-sub">篇 · ${favs.folders.length} 个文件夹</div></div>
    </div>
    <div data-list></div>
  </div>`);
  view().replaceChildren(page);
  const box = $('[data-list]', page);
  if (!items.length) { box.innerHTML = emptyState('clock', '还没有阅读记录，打开任意一篇论文就会自动记录'); return; }
  let curDay = null;
  let card = null;
  for (const it of items) {
    const day = dayLabel(it.last_read);
    if (day !== curDay) {
      curDay = day;
      box.appendChild(h(`<div class="day-title">${esc(day)}</div>`));
      card = h('<div class="card rows"></div>');
      box.appendChild(card);
    }
    const p = it.paper;
    const row = h(`<div class="hrow">
      <div style="min-width:0"><div class="hrow-title">${esc(p.title)}</div>
        <div class="hrow-sub">${esc(p.source || '')}${p.venue && p.venue !== 'arXiv' ? ' · ' + esc(p.venue) : ''} · ${esc((p.authors || []).slice(0, 3).join(', '))}</div></div>
      <div class="hrow-num">${fmtTime(it.last_read)} · 读了 ${fmtDuration(it.seconds)}${it.read_count > 1 ? ` · ${it.read_count} 次` : ''}</div>
      <div class="row-flex actions">
        <button class="icon-btn ${p._fav ? 'fav-on' : ''}" data-fav title="收藏">${icon('star', 16)}</button>
        <button class="icon-btn" data-del title="删除这条记录">${icon('x', 16)}</button>
      </div></div>`);
    row.onclick = e => {
      if (e.target.closest('[data-del]')) {
        e.stopPropagation();
        api.historyDelete(p.id).then(() => { row.remove(); toast('已删除'); });
        return;
      }
      if (e.target.closest('[data-fav]')) {
        e.stopPropagation();
        openFavorite(p, fav => $('[data-fav]', row).classList.toggle('fav-on', !!fav));
        return;
      }
      location.hash = paperUrl(p.id);
    };
    card.appendChild(row);
  }
  const clear = $('[data-clear]', page);
  if (clear) clear.onclick = async () => {
    if (!await confirmDialog('清空阅读记录', '将删除全部阅读记录（收藏、AI 解读和对话不受影响），此操作无法撤销。', { okLabel: '清空', danger: true })) return;
    await api.historyDelete(null);
    route();
  };
}

// ---------- 设置 ----------
export async function openSettings() {
  let st;
  try { st = await api.settings(); } catch (e) { toast(e.message, 'error'); return; }
  const s = st.settings;
  const secret = (key, label, hint) => `<div class="form-row"><span class="form-label">${label}</span>
      <input class="input" type="password" data-k="${key}" placeholder="${s[key] ? '已配置（留空保持不变）' : '未配置'}" autocomplete="off"></div>
      ${hint ? `<div class="set-hint">${hint}</div>` : ''}`;
  const body = h(`<div class="settings form">
    <div class="set-section"><div class="set-title">站长的 AI</div>
      <div class="notice" style="margin-bottom:12px"><span class="state ${st.ai.ok ? 'ok' : 'err'}"></span><div>${esc(st.ai.text)}</div></div>
      <div class="form">
        <div class="form-row"><span class="form-label">调用方式</span><select class="input" data-k="ai_backend">
          <option value="auto">自动（有 Claude Code 订阅就用订阅）</option><option value="cli">只用本机 Claude Code 订阅</option><option value="proxy">只用下面的接口</option></select></div>
        <div class="form-row"><span class="form-label">解读 / 对话模型</span><input class="input" data-k="ai_model" value="${esc(s.ai_model || '')}" placeholder="claude-opus-5-5"></div>
        <div class="form-row"><span class="form-label">思考强度</span><select class="input" data-k="ai_effort">
          ${['low', 'medium', 'high', 'xhigh', 'max'].map(x => `<option value="${x}">${x}</option>`).join('')}</select></div>
        <div class="form-row"><span class="form-label">批量总结模型</span><input class="input" data-k="claude_model" value="${esc(s.claude_model || '')}" placeholder="haiku"></div>
        <div class="form-row"><span class="form-label">接口地址</span><input class="input" data-k="claude_base_url" value="${esc(s.claude_base_url || '')}"></div>
        <div class="set-hint">不用订阅时调用的 Anthropic 兼容接口：本机反代或 https://api.anthropic.com</div>
        ${secret('claude_api_key', 'API Key', '反代未启用鉴权时留空')}
        <div class="form-row"><span class="form-label">全文上限</span><input class="input" data-k="ai_context_chars" type="number" min="10000" step="10000" value="${esc(s.ai_context_chars || 100000)}"></div>
        <div class="set-hint">送给 AI 的论文全文最大字符数</div>
      </div></div>
    <div class="set-section"><div class="set-title">站长密码</div>
      <div class="form"><div class="form-row"><span class="form-label">新密码</span><input class="input" type="password" data-k="owner_password" placeholder="留空不修改" autocomplete="new-password"></div></div></div>
    <div class="set-section"><div class="set-title">数据源</div>
      <div data-eng></div>
      <div class="form" style="margin-top:12px">
        ${secret('ieee_api_key', 'IEEE Xplore', '在 <a href="https://developer.ieee.org/" target="_blank" rel="noopener">developer.ieee.org</a> 免费申请')}
        ${secret('serpapi_key', 'SerpAPI', 'Google Scholar 无官方 API，经 <a href="https://serpapi.com/" target="_blank" rel="noopener">serpapi.com</a> 获取（免费 100 次/月）')}
        ${secret('s2_api_key', 'Semantic Scholar', '可选：免 key 时共享限流，<a href="https://www.semanticscholar.org/product/api#api-key-form" target="_blank" rel="noopener">申请 key</a> 后更稳定')}
        ${secret('openalex_api_key', 'OpenAlex', '可选：<a href="https://openalex.org/settings/api" target="_blank" rel="noopener">openalex.org</a> 免费 key 提高每日额度')}
      </div></div>
  </div>`);
  $('[data-k="ai_backend"]', body).value = s.ai_backend || 'auto';
  $('[data-k="ai_effort"]', body).value = s.ai_effort || 'medium';
  $('[data-eng]', body).innerHTML = st.engines.map(e => `<div class="eng-row"><span class="grow">${esc(e.name)}</span>
    ${e.link_only ? '<span class="state">仅跳转</span>' : e.configured ? '<span class="state ok">可用</span>' : '<span class="state warn">需要 key</span>'}</div>`).join('');
  modal({
    title: '服务器设置', body, width: 640,
    footer: [
      { label: '取消', onClick: c => c() },
      {
        label: '保存', cls: 'btn-primary', onClick: async (close, btn) => {
          const data = {};
          $$('[data-k]', body).forEach(inp => {
            const k = inp.dataset.k;
            const v = inp.value.trim();
            if (inp.type === 'password') { if (v) data[k] = v; } else data[k] = k === 'ai_context_chars' ? (parseInt(v, 10) || 100000) : v;
          });
          btn.disabled = true;
          try {
            await api.saveSettings(data);
            S.meta = null;
            close();
            toast('设置已保存', 'success');
            route();
          } catch (e) { toast(e.message, 'error'); btn.disabled = false; }
        },
      },
    ],
  });
}

// ---------- 启动 ----------
window.openSettings = openSettings;
window.addEventListener('hashchange', route);
document.addEventListener('keydown', e => {
  if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
    const inp = $('.search-pill input');
    if (inp) { e.preventDefault(); inp.focus(); }
  }
});
window.addEventListener('me-changed', renderSidebar);
window.addEventListener('look-changed', renderSidebar);
refreshMe().then(route);
