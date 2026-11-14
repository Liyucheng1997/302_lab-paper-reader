// 外观：纸张颜色、阅读字号、深浅色（存在本浏览器）
import { $$, h, icon } from './ui.js';

export const PAPERS = [
  ['white', '白色', '#ffffff'],
  ['sepia', '米黄', '#f8f2e6'],
  ['green', '豆沙绿', '#eef5ea'],
  ['gray', '浅灰', '#f1f1f3'],
];
const SIZES = [['s', '小'], ['m', '中'], ['l', '大'], ['xl', '特大']];

const get = (k, d) => { try { return localStorage.getItem(k) || d; } catch (e) { return d; } };
const set = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } };

export function look() {
  return {
    paper: get('paper', 'white'),
    fs: get('fontSize', 'm'),
    theme: document.documentElement.getAttribute('data-theme') || 'light',
  };
}

function apply(k, v) {
  const root = document.documentElement;
  if (k === 'paper') { root.setAttribute('data-paper', v); set('paper', v); }
  if (k === 'fs') { root.setAttribute('data-fs', v); set('fontSize', v); }
  if (k === 'theme' && (v === 'light' || v === 'dark')) { root.setAttribute('data-theme', v); set('theme', v); }
  window.dispatchEvent(new Event('look-changed'));
}

let pop = null;
function close() {
  if (pop) { pop.remove(); pop = null; document.removeEventListener('mousedown', onDown, true); }
}
function onDown(e) { if (pop && !pop.contains(e.target)) close(); }

export function openLook(anchor, placement = 'below') {
  if (pop) { close(); return; }
  const L = look();
  pop = h(`<div class="popover look-pop">
    <div class="menu-header">纸张颜色</div>
    <div class="look-swatches">${PAPERS.map(([k, n, c]) => `<button data-paper="${k}" class="${L.paper === k && L.theme !== 'dark' ? 'active' : ''}"><span style="background:${c}"></span>${n}</button>`).join('')}</div>
    <div class="menu-header">阅读字号</div>
    <div class="seg look-seg" data-look-fs>${SIZES.map(([k, n]) => `<button data-k="${k}" class="${L.fs === k ? 'active' : ''}">${n}</button>`).join('')}</div>
    <div class="menu-header">模式</div>
    <div class="seg look-seg" data-look-mode>${[['light', `${icon('sun', 14)}浅色`], ['dark', `${icon('moon', 14)}深色`]].map(([k, n]) => `<button data-k="${k}" class="${L.theme === k ? 'active' : ''}">${n}</button>`).join('')}</div>
  </div>`);
  document.body.appendChild(pop);
  // 注意：<html> 自己带 data-theme / data-fs / data-paper，选择器不能用这些属性名，否则会匹配到弹窗里所有按钮
  const swatches = () => $$('.look-swatches button', pop);
  const fsBtns = () => $$('[data-look-fs] button', pop);
  const modeBtns = () => $$('[data-look-mode] button', pop);
  swatches().forEach(b => b.onclick = () => {
    apply('paper', b.dataset.paper);
    if (look().theme === 'dark') apply('theme', 'light');  // 纸张颜色只在浅色模式下生效
    refresh();
  });
  fsBtns().forEach(b => b.onclick = () => { apply('fs', b.dataset.k); refresh(); });
  modeBtns().forEach(b => b.onclick = () => { apply('theme', b.dataset.k); refresh(); });
  const refresh = () => {
    const L2 = look();
    swatches().forEach(b => b.classList.toggle('active', b.dataset.paper === L2.paper && L2.theme !== 'dark'));
    fsBtns().forEach(b => b.classList.toggle('active', b.dataset.k === L2.fs));
    modeBtns().forEach(b => b.classList.toggle('active', b.dataset.k === L2.theme));
  };
  const r = anchor.getBoundingClientRect();
  const w = pop.offsetWidth;
  const hgt = pop.offsetHeight;
  if (placement === 'right') {
    pop.style.left = Math.min(window.innerWidth - w - 8, r.right + 8) + 'px';
    pop.style.top = Math.max(8, Math.min(window.innerHeight - hgt - 8, r.bottom - hgt)) + 'px';
    pop.style.transformOrigin = 'bottom left';
  } else {
    pop.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.right - w)) + 'px';
    pop.style.top = r.bottom + 6 + 'px';
    pop.style.transformOrigin = 'top right';
  }
  setTimeout(() => document.addEventListener('mousedown', onDown, true), 0);
}
