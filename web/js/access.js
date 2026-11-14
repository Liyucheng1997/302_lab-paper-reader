// 身份与 AI 访问：站长密码解锁 / 访客自己的 API
import { aiHeaders, api, getMyAI, setMyAI } from './api.js';
import { $, $$, esc, h, icon, modal, toast } from './ui.js';

export const ME = { owner: false, has_password: true, ai: null };

export async function refreshMe() {
  try { Object.assign(ME, await api.me()); } catch (e) { /* ignore */ }
  document.body.classList.toggle('is-owner', !!ME.owner);
  window.dispatchEvent(new Event('me-changed'));
  return ME;
}

export function setMe(m) {
  Object.assign(ME, m || {});
  document.body.classList.toggle('is-owner', !!ME.owner);
}

/** 当前能不能用 AI：自己的 API 已填好 → 用自己的；否则需要站长已解锁 */
export function hasAI() {
  return Object.keys(aiHeaders()).length > 0 || ME.owner;
}

/** 一句话说明现在 AI 走哪里（侧栏、面板用） */
export function aiLabel() {
  const c = getMyAI();
  if (c.mode === 'own' && c.key) return { text: `自己的 API · ${c.model || ''}`, cls: 'ok' };
  if (ME.owner) return { text: '站长的 AI · 已解锁', cls: 'ok' };
  return { text: '未开启', cls: '' };
}

/** 需要 AI 时调用：能用返回 true；不能用就弹出设置，返回 false */
export function ensureAI(onReady) {
  if (hasAI()) return true;
  openAiAccess(onReady);
  return false;
}

export function openAiAccess(onReady) {
  const cfg = getMyAI();
  let tab = cfg.mode === 'own' ? 'own' : 'owner';
  const body = h(`<div style="width:100%">
    <p class="modal-msg" style="margin-bottom:14px">AI 解读和伴读对话需要调用大模型。可以输入站长密码使用站长的 Claude，也可以填写你自己的 API（只保存在你的浏览器里，服务器只转发、不保存）。</p>
    <div class="seg" data-tab style="margin-bottom:16px"><button data-k="owner">站长的 AI</button><button data-k="own">我自己的 API</button></div>
    <div data-pane="owner"></div>
    <div data-pane="own" class="form">
      <div class="form-row"><span class="form-label">接口格式</span>
        <select class="input" data-f="format"><option value="anthropic">Anthropic（Claude）</option><option value="openai">OpenAI 兼容（DeepSeek、通义、Kimi 等）</option></select></div>
      <div class="form-row"><span class="form-label">API 地址</span><input class="input" data-f="base" placeholder="https://api.anthropic.com"></div>
      <div class="set-hint" data-basehint></div>
      <div class="form-row"><span class="form-label">API Key</span><input class="input" type="password" data-f="key" autocomplete="off" placeholder="sk-..."></div>
      <div class="form-row"><span class="form-label">模型</span><input class="input" data-f="model" placeholder="claude-opus-5-5"></div>
      <div class="row-flex" style="margin-top:4px"><button class="btn btn-sm" data-test>${icon('sparkles', 14)}测试连接</button><span data-testres class="muted" style="font-size:12.5px"></span>
        <button class="btn btn-sm btn-danger" data-clear style="margin-left:auto">清除</button></div>
    </div>
  </div>`);

  const ownerPane = $('[data-pane="owner"]', body);
  const renderOwner = () => {
    if (ME.owner) {
      ownerPane.innerHTML = `<div class="notice">${icon('sparkles', 16)}<div><b>已解锁站长的 AI</b><br>${esc(ME.ai?.text || '')}</div></div>
        <div class="row-flex" style="margin-top:12px"><button class="btn btn-sm" data-lock>${icon('x', 14)}退出站长身份</button></div>`;
      $('[data-lock]', ownerPane).onclick = async () => {
        await api.lock();
        await refreshMe();
        toast('已退出站长身份');
        m.close();
        location.reload();
      };
    } else {
      ownerPane.innerHTML = `<div class="form">
        <div class="form-row"><span class="form-label">站长密码</span><input class="input" type="password" data-pw autocomplete="current-password" inputmode="numeric"></div>
        <div class="set-hint">解锁后在这台设备上保持 90 天，你的阅读记录和收藏会切换到站长账号。</div>
      </div>`;
      const pw = $('[data-pw]', ownerPane);
      pw.onkeydown = e => { if (e.key === 'Enter') save(m.close, null); };
      setTimeout(() => pw.focus(), 50);
    }
  };

  const f = k => $(`[data-f="${k}"]`, body);
  f('format').value = cfg.format || 'anthropic';
  f('base').value = cfg.base || '';
  f('key').value = cfg.key || '';
  f('model').value = cfg.model || '';
  const hint = () => {
    const isAnth = f('format').value === 'anthropic';
    f('base').placeholder = isAnth ? 'https://api.anthropic.com' : 'https://api.deepseek.com/v1';
    f('model').placeholder = isAnth ? 'claude-opus-5-5' : 'deepseek-chat';
    $('[data-basehint]', body).textContent = isAnth
      ? '留空即 Anthropic 官方地址；也可以填其他 Anthropic 兼容地址'
      : '填到 /v1 为止，服务器会自动加 /chat/completions';
  };
  f('format').onchange = hint;
  hint();
  const readOwn = () => ({ mode: 'own', format: f('format').value, base: f('base').value.trim(), key: f('key').value.trim(), model: f('model').value.trim() });

  $('[data-test]', body).onclick = async () => {
    const c = readOwn();
    const res = $('[data-testres]', body);
    if (!c.key || !c.model) { res.textContent = '请先填写 Key 和模型'; return; }
    res.textContent = '测试中…';
    const enc = encodeURIComponent;
    try {
      const r = await api.aiTest({ 'X-AI-Format': enc(c.format), 'X-AI-Base': enc(c.base), 'X-AI-Key': enc(c.key), 'X-AI-Model': enc(c.model) });
      res.innerHTML = `<span class="state ok">连接成功：${esc(r.reply)}</span>`;
    } catch (e) { res.innerHTML = `<span class="state err">${esc(e.message)}</span>`; }
  };
  $('[data-clear]', body).onclick = () => {
    setMyAI({ mode: 'owner' });
    ['base', 'key', 'model'].forEach(k => { f(k).value = ''; });
    toast('已清除你的 API 配置');
  };

  const renderTab = () => {
    $$('[data-tab] button', body).forEach(b => b.classList.toggle('active', b.dataset.k === tab));
    $$('[data-pane]', body).forEach(p => p.classList.toggle('hidden', p.dataset.pane !== tab));
    if (tab === 'owner') renderOwner();
  };
  $$('[data-tab] button', body).forEach(b => b.onclick = () => { tab = b.dataset.k; renderTab(); });

  const save = async (close, btn) => {
    if (tab === 'owner') {
      if (ME.owner) {
        setMyAI({ ...getMyAI(), mode: 'owner' });
        close();
        onReady && onReady();
        window.dispatchEvent(new Event('me-changed'));
        return;
      }
      const pw = $('[data-pw]', body).value;
      if (!pw) { toast('请输入密码'); return; }
      if (btn) btn.disabled = true;
      try {
        await api.unlock(pw);
        setMyAI({ ...getMyAI(), mode: 'owner' });
        await refreshMe();
        close();
        toast('已解锁站长的 AI', 'success');
        onReady && onReady();
        location.reload();
      } catch (e) {
        toast(e.message, 'error');
        if (btn) btn.disabled = false;
      }
      return;
    }
    const c = readOwn();
    if (!c.key || !c.model) { toast('请填写 API Key 和模型'); return; }
    setMyAI(c);
    close();
    toast('已保存，AI 将使用你自己的 API', 'success');
    window.dispatchEvent(new Event('me-changed'));
    onReady && onReady();
  };

  const m = modal({
    title: 'AI 设置', body, width: 560,
    footer: [{ label: '取消', onClick: c => c() }, { label: '确定', cls: 'btn-primary', onClick: save }],
  });
  renderTab();
}
