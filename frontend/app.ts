import { ApiError, checkDownload, request } from './api.js';
import { SessionController } from './session.js';
import { UploadQueue } from './features/uploads.js';
import { Preferences } from './ui/preferences.js';
import { Dialogs } from './ui/dialog.js';
import { View, type ViewName } from './ui/view.js';
import { element, escape as e, copy } from './ui/dom.js';
import { icon } from './icons.js';

const credentials = new URLSearchParams(location.hash.slice(1));
const desktopClient = document.body.dataset.client === 'desktop' || credentials.has('admin');
const busy = new Set<string>();
let toastTimer = 0, pollTimer = 0, paused = false;
const preferences = new Preferences(() => render());
const view = new View(preferences);
const dialogs = new Dialogs();
const session = new SessionController(() => render(), undefined, desktopClient);
const uploads = new UploadQueue(element('#transfers'), () => session.invalidate(), toast);

function toast(message: string, error = false): void {
  clearTimeout(toastTimer);
  const node = element('#toast'); node.innerHTML = `${icon(error ? 'help' : 'check')}<span>${e(message)}</span>`; node.className = `toast visible ${error ? 'error' : ''}`;
  toastTimer = window.setTimeout(() => { node.className = 'toast'; }, 6000);
}
const report = (error: unknown): void => toast(error instanceof Error ? error.message : '操作失败，请重试。', true);
function render(): void {
  view.render(session.connection);
  if (busy.has('native-picker')) document.querySelectorAll<HTMLButtonElement>('[data-action="add-files"],[data-action="pick-folder"]').forEach(button => { button.disabled = true; });
  document.title = `隔空传${session.connection.snapshot?.role === 'admin' ? ' · 电脑端' : session.connection.snapshot ? ' · 手机端' : ''}`;
}
async function run(key: string, operation: () => Promise<void>): Promise<void> {
  if (busy.has(key)) { toast('这项操作正在处理，请稍候。'); return; }
  busy.add(key); render();
  try { await operation(); } finally { busy.delete(key); render(); }
}
function connected(): void { if (session.connection.phase !== 'connected') throw new ApiError('连接尚未恢复，请检查电脑程序和 Wi-Fi。', 0); }
function route(): void {
  const value = new URLSearchParams(location.search).get('view');
  view.view = value === 'received' || value === 'activity' ? value : 'shared'; view.query = ''; view.filter = 'all';
  const search = document.querySelector<HTMLInputElement>('#search-input'); if (search) search.value = '';
  render();
}
function chooseView(next: string | undefined): void {
  if (!['shared','received','activity'].includes(next ?? '') || session.connection.snapshot?.role !== 'admin') return;
  const url = new URL(location.href); if (next === 'shared') url.searchParams.delete('view'); else url.searchParams.set('view', next!);
  history.pushState(null, '', url.pathname + url.search); route();
}
function schedulePoll(): void {
  clearTimeout(pollTimer);
  if (!paused && ['connected','reconnecting'].includes(session.connection.phase)) pollTimer = window.setTimeout(() => { void session.refresh().finally(schedulePoll); }, document.hidden ? 8000 : 3000);
}
async function start(): Promise<void> {
  await session.connect(async signal => {
    const values = new URLSearchParams(location.hash.slice(1));
    const admin = values.get('admin'), pair = values.get('pair');
    try { if (admin || pair) await request('/api/session', { role: admin ? 'admin' : 'phone', token: admin ?? pair }, { signal }); }
    finally { if (admin || pair) history.replaceState(null, '', location.pathname + location.search); }
  });
  route(); schedulePoll();
}
function help(): void {
  dialogs.open('使用帮助', `<div class="help-content"><h3>电脑发送到手机</h3><p>添加文件，或选择项目的安装包输出文件夹。手机扫描二维码，在浏览器中打开链接后下载。APK 下载后可在文件管理器中打开安装；AAB 不能直接安装。</p><h3>手机发送到电脑</h3><p>选择「发送文件到电脑」。看到「已保存到电脑」后，在电脑的「收到的文件」中查看。单个上传文件最大 8 GB，同名文件会自动另存。</p><h3>扫码打不开</h3><ol><li>手机和电脑连接同一个 Wi-Fi；电脑用网线连接同一台路由器也可以。</li><li>在系统浏览器中打开链接。微信中可通过菜单选择「在浏览器打开」。</li><li>检查 Windows 防火墙是否允许隔空传通过你信任的专用网络。</li><li>检查 VPN、访客 Wi-Fi 和路由器的设备隔离。有多个网卡时可切换二维码下面的地址。</li></ol><h3>保存与退出</h3><p>关闭网页后，电脑程序仍然运行。选择「退出程序」停止连接。移除共享不会删除原文件；拖入网页的文件会复制到电脑的待发送目录。</p><p class="help-note">传输使用局域网 HTTP，适合信任的家庭或开发网络。二维码包含临时连接凭据，需要撤销访问时选择「重置连接」。下载进度和续传由浏览器管理。</p></div><div class="dialog-actions"><button class="button primary" data-action="close-dialog">关闭帮助</button></div>`);
}
function settings(): void {
  const state = session.connection.snapshot;
  const generation = dialogs.open('设置', `<label class="field-label" for="theme-select">外观</label><select class="path-input" id="theme-select"><option value="auto" ${preferences.theme === 'auto' ? 'selected' : ''}>跟随系统</option><option value="light" ${preferences.theme === 'light' ? 'selected' : ''}>浅色</option><option value="dark" ${preferences.theme === 'dark' ? 'selected' : ''}>深色</option></select><p class="field-help">外观和连接信息显示方式只保存在当前浏览器。</p>${state?.role === 'admin' ? `<form id="name-form"><label class="field-label" for="computer-display-name">电脑名称</label><input id="computer-display-name" class="path-input" value="${e(state.computer)}" maxlength="64" required /><div class="dialog-actions"><button class="button primary" type="submit">保存电脑名称</button></div></form>` : '<div class="dialog-actions"><button class="button primary" data-action="close-dialog">完成</button></div>'}`);
  document.querySelector<HTMLFormElement>('#name-form')?.addEventListener('submit', event => {
    event.preventDefault(); const input = element<HTMLInputElement>('#computer-display-name');
    const name = input.value; dialogs.pending(generation, true);
    void run('save-name', async () => {
      try { await request('/api/admin/computer-name', { name }); await session.invalidate(); dialogs.close(generation); toast('电脑名称已保存。'); }
      catch (error) { dialogs.error(generation, error); }
      finally { dialogs.pending(generation, false); }
    });
  });
}
function folderDialog(): void {
  const generation = dialogs.open('添加安装包文件夹', `<p class="dialog-copy">选择项目的输出目录，例如 app/build/outputs/apk。新的安装包写入完成后会自动显示。</p><button class="button primary full-width" data-action="pick-folder">${icon('folder')}浏览电脑文件夹</button><div class="dialog-or">或输入完整路径</div><form id="folder-form"><label class="field-label" for="folder-path">文件夹路径</label><input class="path-input" id="folder-path" placeholder="例如 D:/Projects/MyApp/app/build/outputs/apk" required autocomplete="off" /><div class="dialog-actions"><button type="button" class="button secondary" data-action="close-dialog">取消</button><button class="button primary" type="submit">添加文件夹</button></div></form>`);
  const input = element<HTMLInputElement>('#folder-path');
  element('#folder-form').addEventListener('submit', event => {
    event.preventDefault();
    const path = input.value; dialogs.pending(generation, true);
    void run('folder-write', async () => {
      try { await request('/api/admin/add-folder', { path }); await session.invalidate(); dialogs.close(generation); toast('共享文件夹已添加。'); }
      catch (error) { dialogs.error(generation, error); }
      finally { dialogs.pending(generation, false); }
    });
  });
}
async function action(button: HTMLElement): Promise<void> {
  const name = button.dataset.action, identifier = button.dataset.id ?? '';
  if (name === 'close-dialog') { dialogs.close(); return; }
  if (name === 'confirm-dialog') return dialogs.accept();
  if (name === 'help') return help();
  if (name === 'preferences') return settings();
  if (name === 'privacy') { preferences.togglePrivacy(); return; }
  if (name === 'retry') { await session.refresh(); schedulePoll(); return; }
  if (name === 'check-upload') return uploads.check(identifier);
  if (name === 'cancel-upload') return uploads.cancel(identifier);
  if (name === 'cancel-all') return uploads.cancelAll();
  if (name === 'clear-transfers') { uploads.clear(); return; }
  if (name === 'retry-upload') { connected(); uploads.retry(identifier); return; }
  if (name === 'view') { chooseView(button.dataset.view); return; }
  if (name === 'filter') { view.filter = button.dataset.filter ?? 'all'; render(); return; }
  connected();
  const state = session.connection.snapshot!;
  if (name === 'add-files') {
    if (state.role !== 'admin') { element<HTMLInputElement>('#file-input').click(); return; }
    return run('native-picker', async () => {
      try { await request('/api/admin/pick-files', {}, { timeout: 610000 }); await session.invalidate(); }
      catch (error) { if (error instanceof ApiError && error.code === 'desktop-unavailable') element<HTMLInputElement>('#file-input').click(); else throw error; }
    });
  }
  if (name === 'add-folder') return folderDialog();
  if (name === 'pick-folder') {
    const generation = dialogs.current();
    return run('native-picker', async () => {
      try { await request('/api/admin/pick-folder', {}, { timeout: 610000 }); await session.invalidate(); dialogs.close(generation); }
      catch (error) { dialogs.error(generation, error); }
    });
  }
  if (name === 'refresh') return run('refresh', async () => { if (state.role === 'admin') await request('/api/admin/refresh', {}); await session.invalidate(); });
  if (name === 'copy-link') { await copy(state.pairUrl!); toast('手机连接链接已复制。'); return; }
  if (name === 'open-inbox') { await request('/api/admin/open-inbox', {}); return; }
  if (name === 'download') {
    const path = button.getAttribute('href'); if (!path || !/^\/download\/[a-f0-9]{24}(\?received=1)?$/.test(path)) return;
    const epoch = session.epoch;
    return run(`download-${path}`, async () => { await checkDownload(path); if (epoch !== session.epoch || session.connection.phase !== 'connected') return; const link = document.createElement('a'); link.href = path; link.download = ''; document.body.append(link); link.click(); link.remove(); });
  }
  if (name === 'remove-file') return run(`remove-${identifier}`, async () => { await request('/api/admin/remove-file', { id: identifier }); await session.invalidate(); toast('已取消共享，原文件保留。'); });
  if (name === 'remove-folder') { dialogs.confirm('移除共享文件夹', '手机将看不到来自这个文件夹的安装包。电脑上的原文件会保留。', '移除共享', async () => { await request('/api/admin/remove-folder', { id: identifier }); await session.invalidate(); }); return; }
  if (name === 'reset-pairs') { dialogs.confirm('重置手机连接', '已连接的手机会断开，旧二维码和链接会失效。手机需要重新扫码。', '重置连接', async () => { await request('/api/admin/reset-pairs', {}); await session.invalidate(); }); return; }
  if (name === 'revoke') { dialogs.confirm('断开设备', '该设备需要重新扫码才能继续上传和下载。', '断开设备', async () => { await request('/api/admin/revoke-device', { id: identifier }); await session.invalidate(); }); return; }
  if (name === 'recover-settings') { dialogs.confirm('备份并恢复共享设置', '程序会保留原始设置的备份，然后新建空的共享列表。收到的文件和电脑上的原文件会保留。', '备份并恢复', async () => { await request('/api/admin/recover-settings', {}); await session.invalidate(); toast('原设置已备份，可以重新添加共享文件。'); }); return; }
  if (name === 'shutdown') { dialogs.confirm('退出隔空传', `${state.activeTransfers ? `当前有 ${state.activeTransfers} 个传输任务。` : ''}退出会中断未完成的传输，已保存的文件和共享目录会保留。`, '退出程序', async () => { await request('/api/admin/shutdown', {}); uploads.dispose(); clearTimeout(pollTimer); paused = true; session.stop(); }); }
}

document.addEventListener('click', event => {
  const button = (event.target as Element).closest<HTMLElement>('[data-action]'); if (!button || button.hasAttribute('disabled')) return;
  event.preventDefault(); button.setAttribute('disabled', '');
  void action(button).catch(report).finally(() => { button.removeAttribute('disabled'); render(); });
});
document.addEventListener('input', event => { if ((event.target as HTMLElement).id === 'search-input') { view.query = (event.target as HTMLInputElement).value; render(); } });
document.addEventListener('change', event => {
  const input = event.target as HTMLInputElement;
  if (input.id === 'theme-select') preferences.setTheme(input.value);
  if (input.id === 'address-select') void run('address', async () => { await request('/api/admin/address', { address: input.value }); await session.invalidate(); }).catch(report);
  if (input.id === 'file-input') { try { connected(); uploads.add(Array.from(input.files ?? [])); } catch (error) { report(error); } input.value = ''; }
});
let dragDepth = 0;
document.addEventListener('dragenter', event => { if (event.dataTransfer?.types.includes('Files')) { event.preventDefault(); dragDepth++; document.querySelector('#drop-zone')?.classList.add('drag-over'); } });
document.addEventListener('dragover', event => { if (event.dataTransfer?.types.includes('Files')) event.preventDefault(); });
document.addEventListener('dragleave', () => { if (--dragDepth <= 0) document.querySelector('#drop-zone')?.classList.remove('drag-over'); });
document.addEventListener('drop', event => {
  event.preventDefault(); dragDepth = 0; document.querySelector('#drop-zone')?.classList.remove('drag-over');
  try {
    connected(); if (view.view !== 'shared') { toast('请切换到发送文件页面后再拖入文件。', true); return; }
    const items = Array.from(event.dataTransfer?.items ?? []);
    const directory = items.some(item => item.webkitGetAsEntry?.()?.isDirectory);
    if (directory) toast('文件夹请通过「添加安装包文件夹」选择。', true);
    const files = items.length ? items.filter(item => item.kind === 'file' && !item.webkitGetAsEntry?.()?.isDirectory).map(item => item.getAsFile()).filter((file): file is File => file !== null) : Array.from(event.dataTransfer?.files ?? []);
    uploads.add(files);
  } catch (error) { report(error); }
});
window.addEventListener('popstate', route);
window.addEventListener('hashchange', () => { const values = new URLSearchParams(location.hash.slice(1)); if (values.has('admin') || values.has('pair')) location.reload(); });
document.addEventListener('visibilitychange', () => { if (!document.hidden && !paused) void session.refresh().finally(schedulePoll); });
window.addEventListener('pagehide', () => { paused = true; clearTimeout(pollTimer); uploads.dispose(); session.stop(); preferences.dispose(); });
window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
void start().catch(report);
