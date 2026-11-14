// 收藏编辑弹窗：文件夹（多选）、阅读状态、标签、笔记
import { api } from './api.js';
import { $, $$, esc, h, icon, modal, promptDialog, toast } from './ui.js';

const STATUS = [['todo', '待读'], ['reading', '在读'], ['done', '已读']];

export async function openFavorite(paper, onChange) {
  let folders = [];
  let fav = null;
  let suggestion = null;
  try {
    const [f, d, s] = await Promise.all([
      api.folders(),
      api.paper(paper.id),
      api.favoriteSuggest(paper.id).catch(() => ({})),
    ]);
    folders = f.folders;
    fav = d.favorite;
    suggestion = s.suggestion;
  } catch (e) {
    toast(e.message, 'error');
    return;
  }
  const isNew = !fav;
  const selected = new Set(fav ? fav.folder_ids : (suggestion ? [suggestion.folder_id] : []));
  let status = fav ? fav.status : 'todo';

  const body = h(`<div>
    <div style="font-size:14px;font-weight:600;line-height:1.5;margin-bottom:4px">${esc(paper.title)}</div>
    <div class="field-label">放入文件夹</div>
    <div class="fav-folders"></div>
    <button class="btn btn-ghost btn-sm" data-new style="margin-top:6px">${icon('plus', 14)}新建文件夹</button>
    <div class="field-label">阅读状态</div>
    <div class="seg" data-status>${STATUS.map(([k, n]) => `<button data-k="${k}">${n}</button>`).join('')}</div>
    <div class="field-label">标签（用逗号或空格分隔）</div>
    <input class="input" data-tags style="width:100%;height:36px" placeholder="如：MPC, 必读, 组会">
    <div class="field-label">笔记</div>
    <textarea class="input" data-note rows="4" style="width:100%" placeholder="记录你的想法、待验证的问题……"></textarea>
  </div>`);

  const renderFolders = () => {
    const box = $('.fav-folders', body);
    box.innerHTML = folders.length ? '' : '<div class="muted" style="padding:6px 8px;font-size:13px">还没有文件夹，新建一个来分类整理吧</div>';
    for (const f of folders) {
      const row = h(`<label class="fav-folder"><input type="checkbox" ${selected.has(f.id) ? 'checked' : ''}>${icon('folder', 16)}<span>${esc(f.name)}</span>
        ${suggestion && suggestion.folder_id === f.id ? '<span class="hint">推荐</span>' : ''}</label>`);
      $('input', row).onchange = e => { e.target.checked ? selected.add(f.id) : selected.delete(f.id); };
      box.appendChild(row);
    }
  };
  renderFolders();

  const renderStatus = () => $$('[data-status] button', body).forEach(b => b.classList.toggle('active', b.dataset.k === status));
  renderStatus();
  $$('[data-status] button', body).forEach(b => b.onclick = () => { status = b.dataset.k; renderStatus(); });

  $('[data-tags]', body).value = fav ? fav.tags.join(', ') : ((paper.summary || {}).tags || []).slice(0, 3).join(', ');
  $('[data-note]', body).value = fav ? fav.note : '';

  $('[data-new]', body).onclick = async () => {
    const name = await promptDialog('新建文件夹', '', '如：车辆动力学、强化学习、组会待讲');
    if (!name || !name.trim()) return;
    try {
      const r = await api.folderCreate(name.trim());
      folders = r.folders;
      selected.add(r.id);
      renderFolders();
    } catch (e) { toast(e.message, 'error'); }
  };

  const save = async (close, btn) => {
    btn.disabled = true;
    const tags = $('[data-tags]', body).value.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean);
    try {
      const r = await api.favoriteSet(paper.id, {
        folder_ids: [...selected], status, tags, note: $('[data-note]', body).value,
      });
      close();
      toast(isNew ? '已收藏' : '已保存', 'success');
      onChange && onChange(r.favorite);
    } catch (e) { toast(e.message, 'error'); btn.disabled = false; }
  };

  const footer = [];
  if (!isNew) {
    footer.push({
      label: '取消收藏', cls: 'btn-danger', left: true, onClick: async close => {
        try {
          await api.favoriteDelete(paper.id);
          close();
          toast('已取消收藏');
          onChange && onChange(null);
        } catch (e) { toast(e.message, 'error'); }
      },
    });
  }
  footer.push({ label: '取消', onClick: c => c() });
  footer.push({ label: isNew ? '收藏' : '保存', cls: 'btn-primary', onClick: save });
  modal({ title: isNew ? '收藏论文' : '编辑收藏', body, footer, width: 480 });
}
