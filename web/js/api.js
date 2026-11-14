// 后端 API 封装

// 访客自己的 AI 配置：只存在本浏览器，每次 AI 请求带给服务器转发，服务器不保存
const AI_KEY = 'myAI';
export function getMyAI() {
  try { return JSON.parse(localStorage.getItem(AI_KEY) || 'null') || { mode: 'owner' }; } catch (e) { return { mode: 'owner' }; }
}
export function setMyAI(cfg) {
  try { localStorage.setItem(AI_KEY, JSON.stringify(cfg)); } catch (e) { /* ignore */ }
}
export function aiHeaders() {
  const c = getMyAI();
  if (c.mode !== 'own' || !c.key) return {};
  const enc = encodeURIComponent;
  return { 'X-AI-Format': enc(c.format || 'anthropic'), 'X-AI-Base': enc(c.base || ''), 'X-AI-Key': enc(c.key), 'X-AI-Model': enc(c.model || '') };
}

async function request(method, url, body, extraHeaders) {
  const opt = { method, headers: { ...(extraHeaders || {}) } };
  if (body !== undefined) {
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(body);
  }
  let resp;
  try {
    resp = await fetch(url, opt);
  } catch (e) {
    throw new Error('无法连接服务器，请检查网络或稍后再试');
  }
  let data = {};
  try { data = await resp.json(); } catch (e) { /* 非 JSON */ }
  if (!resp.ok) {
    const err = new Error(data.error || `请求失败 (${resp.status})`);
    err.code = data.code;
    err.status = resp.status;
    throw err;
  }
  return data;
}

const qs = obj => new URLSearchParams(Object.entries(obj).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString();

export const api = {
  meta: () => request('GET', '/api/meta'),
  feed: (field) => request('GET', '/api/feed?' + qs({ field })),
  search: (params) => request('GET', '/api/search?' + qs(params)),
  paper: (id) => request('GET', '/api/paper?' + qs({ id })),
  fulltext: (id, force) => request('GET', '/api/fulltext?' + qs({ id, force: force ? 1 : '' })),
  similar: (id, web = true) => request('GET', '/api/similar?' + qs({ id, web: web ? 1 : 0 })),
  recommend: (params = {}) => request('GET', '/api/recommend?' + qs(params)),
  history: () => request('GET', '/api/history'),
  historyOpen: (id) => request('POST', '/api/history/open', { id }),
  historyTick: (id, seconds) => request('POST', '/api/history/tick', { id, seconds }),
  historyDelete: (id) => request('POST', '/api/history/delete', { id }),
  folders: () => request('GET', '/api/folders'),
  folderCreate: (name) => request('POST', '/api/folders/create', { name }),
  folderRename: (id, name) => request('POST', '/api/folders/rename', { id, name }),
  folderDelete: (id) => request('POST', '/api/folders/delete', { id }),
  favorites: () => request('GET', '/api/favorites'),
  favoriteSet: (id, data) => request('POST', '/api/favorites/set', { id, ...data }),
  favoriteDelete: (id) => request('POST', '/api/favorites/delete', { id }),
  favoriteSuggest: (id) => request('GET', '/api/favorites/suggest?' + qs({ id })),
  dismiss: (id) => request('POST', '/api/dismiss', { id }),
  analyze: (id, force) => request('POST', '/api/analyze', { id, force: !!force }, aiHeaders()),
  aiTest: (headers) => request('POST', '/api/ai/test', {}, headers || aiHeaders()),
  me: () => request('GET', '/api/me'),
  unlock: (password) => request('POST', '/api/unlock', { password }),
  lock: () => request('POST', '/api/lock', {}),
  chatClear: (id) => request('POST', '/api/chat/clear', { id }),
  settings: () => request('GET', '/api/settings'),
  saveSettings: (data) => request('POST', '/api/settings', data),
  update: (action) => request('POST', '/api/update', { action }),
  status: () => request('GET', '/api/status'),
};

// 伴读对话：读取 SSE 流
export async function chatStream(body, onEvent, signal) {
  const resp = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...aiHeaders() },
    body: JSON.stringify(body),
    signal,
  });
  if (!resp.ok) {
    let msg = `请求失败 (${resp.status})`;
    let code;
    try { const d = await resp.json(); msg = d.error || msg; code = d.code; } catch (e) { /* ignore */ }
    const err = new Error(msg);
    err.code = code;
    throw err;
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      for (const line of chunk.split('\n')) {
        if (line.startsWith('data: ')) {
          try { onEvent(JSON.parse(line.slice(6))); } catch (e) { /* ignore */ }
        }
      }
    }
  }
}
