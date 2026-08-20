let DB = { papers: [] };
let FIELDS = {};
let state = { field: "", search: "", source: "", onlySummarized: false };

const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function load() {
  const [db, cfg] = await Promise.all([
    fetch("data/papers.json").then(r => r.json()),
    fetch("config.json").then(r => r.json()),
  ]);
  DB = db;
  FIELDS = cfg.fields;
  document.getElementById("updated").textContent = db.updated ? `更新于 ${db.updated}` : "";
  renderTabs();
  render();
}

function renderTabs() {
  const counts = {};
  for (const p of DB.papers) counts[p.field] = (counts[p.field] || 0) + 1;
  const nav = document.getElementById("field-tabs");
  const tabs = [["", "全部", DB.papers.length], ...Object.entries(FIELDS).map(([k, v]) => [k, v.name, counts[k] || 0])];
  nav.innerHTML = tabs.map(([k, name, n]) =>
    `<button data-field="${k}" class="${state.field === k ? "active" : ""}">${name}<span class="n">${n}</span></button>`
  ).join("");
  nav.querySelectorAll("button").forEach(b => b.onclick = () => {
    state.field = b.dataset.field;
    renderTabs();
    render();
  });
}

function matches(p) {
  if (state.field && p.field !== state.field) return false;
  if (state.source && p.source !== state.source) return false;
  if (state.onlySummarized && !p.summary) return false;
  if (state.search) {
    const q = state.search.toLowerCase();
    const hay = [p.title, p.abstract, p.venue, (p.authors || []).join(" "),
      p.summary?.tldr, (p.summary?.points || []).join(" "), (p.summary?.tags || []).join(" ")
    ].join(" ").toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}

function card(p) {
  const s = p.summary;
  return `<article class="card">
    <div class="card-top">
      <span class="badge ${esc(p.source)}">${esc(p.source)}</span>
      <span class="field-badge">${esc(FIELDS[p.field]?.name || p.field)}</span>
      ${p.venue && p.venue !== "arXiv" ? `<span class="venue">${esc(p.venue)}</span>` : ""}
      <span class="date">${esc(p.published)}</span>
    </div>
    <h2><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a></h2>
    <div class="authors">${esc((p.authors || []).slice(0, 8).join(", "))}${(p.authors || []).length > 8 ? " 等" : ""}</div>
    ${s ? `
      <div class="tldr">💡 ${esc(s.tldr)}</div>
      ${s.points?.length ? `<ul class="points">${s.points.map(pt => `<li>${esc(pt)}</li>`).join("")}</ul>` : ""}
      ${s.tags?.length ? `<div class="tags">${s.tags.map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div>` : ""}
    ` : `<div class="no-summary">尚未生成总结 —— 运行 python scripts/summarize.py</div>`}
    ${p.abstract ? `<details class="abstract"><summary>原文摘要</summary><p>${esc(p.abstract)}</p></details>` : ""}
    <div class="links">
      <a href="${esc(p.url)}" target="_blank" rel="noopener">原文链接</a>
      ${p.pdf ? `<a href="${esc(p.pdf)}" target="_blank" rel="noopener">PDF</a>` : ""}
    </div>
  </article>`;
}

function render() {
  const list = DB.papers.filter(matches);
  document.getElementById("count").textContent = `共 ${list.length} 篇`;
  const main = document.getElementById("paper-list");
  main.innerHTML = list.length
    ? list.map(card).join("")
    : `<div class="empty">没有符合条件的论文。<br>运行 <code>python scripts/update.py</code> 抓取并总结最新论文。</div>`;
}

// ---------- 更新功能 ----------
const updateBtn = document.getElementById("update-btn");
const updatePanel = document.getElementById("update-panel");
const updateLog = document.getElementById("update-log");
const updateTitle = document.getElementById("update-title");
let pollTimer = null;

const ACTION_NAMES = { all: "抓取 + 总结", fetch: "抓取论文", summarize: "生成总结" };

async function startUpdate() {
  const action = document.getElementById("update-action").value;
  updateBtn.disabled = true;
  try {
    const resp = await fetch("/api/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      alert(data.error || "启动失败");
      updateBtn.disabled = false;
      return;
    }
    showPanel();
    startPolling();
  } catch (e) {
    alert("无法连接服务器 API。请确认是通过 python serve.py 启动的网站（而非 http.server）。");
    updateBtn.disabled = false;
  }
}

function showPanel() {
  updatePanel.hidden = false;
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(pollStatus, 2000);
  pollStatus();
}

async function pollStatus() {
  let st;
  try {
    st = await fetch("/api/status").then(r => r.json());
  } catch { return; }
  if (st.log?.length || st.running) showPanel();
  const atBottom = updateLog.scrollHeight - updateLog.scrollTop - updateLog.clientHeight < 30;
  updateLog.textContent = (st.log || []).join("\n");
  if (atBottom) updateLog.scrollTop = updateLog.scrollHeight;
  if (st.running) {
    if (!pollTimer) pollTimer = setInterval(pollStatus, 2000);
    updateBtn.disabled = true;
    updateTitle.textContent = `⏳ 正在${ACTION_NAMES[st.action] || "更新"}...（可离开页面，任务在服务器继续运行）`;
  } else {
    updateBtn.disabled = false;
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    if (st.exit_code === null) {
      updatePanel.hidden = true;
    } else {
      updateTitle.textContent = st.exit_code === 0 ? "✅ 更新完成" : "❌ 更新失败，详见日志";
      if (st.exit_code === 0) await reloadData();
    }
  }
}

async function reloadData() {
  DB = await fetch("data/papers.json").then(r => r.json());
  document.getElementById("updated").textContent = DB.updated ? `更新于 ${DB.updated}` : "";
  renderTabs();
  render();
}

updateBtn.addEventListener("click", startUpdate);
document.getElementById("update-close").addEventListener("click", () => { updatePanel.hidden = true; });

document.getElementById("search").addEventListener("input", e => { state.search = e.target.value.trim(); render(); });
document.getElementById("source-filter").addEventListener("change", e => { state.source = e.target.value; render(); });
document.getElementById("only-summarized").addEventListener("change", e => { state.onlySummarized = e.target.checked; render(); });

load().then(pollStatus).catch(err => {
  document.getElementById("paper-list").innerHTML =
    `<div class="empty">加载数据失败: ${esc(err.message)}<br>请先运行 <code>python scripts/fetch_papers.py</code> 生成 data/papers.json，并通过 http 服务访问本页面。</div>`;
});
