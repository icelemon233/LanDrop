import type { Snapshot } from '../models.js';
import type { Connection } from '../session.js';
import { icon } from '../icons.js';
import { escape as e, element, html, size, date } from './dom.js';
import { renderFiles } from '../features/files.js';
import type { Preferences } from './preferences.js';
import { renderSettings } from './settings.js';

export type ViewName = 'shared' | 'received' | 'activity' | 'settings';
export class View {
  view: ViewName = 'shared'; query = ''; filter = 'all';
  private role = '';
  private pair = '';
  constructor(private preferences: Preferences, private root = element('#app')) {}
  render(connection: Connection): void {
    const state = connection.snapshot;
    if (!state) {
      this.role = '';
      const desktop = document.body.dataset.client === 'desktop' || new URLSearchParams(location.hash.slice(1)).has('admin');
      const heading = connection.phase === 'starting' ? '正在连接电脑' : connection.phase === 'stopped' ? '正在退出 LanDrop' : desktop ? '重新打开电脑端' : '连接电脑';
      html(this.root, `<main class="locked-screen"><img src="/assets/cinna-icon.png" alt="LanDrop图标" width="88" height="88" /><h1>${heading}</h1><p>${e(connection.phase === 'stopped' ? '可以关闭此页面。下次双击程序继续使用。' : connection.phase === 'starting' ? '正在读取文件和连接状态…' : connection.error)}</p>${connection.phase !== 'starting' && connection.phase !== 'stopped' ? `<div class="locked-steps">${desktop ? `<span>${icon('computer')}关闭报错页面，重新双击新版 LanDrop 程序。</span>` : `<span>${icon('wifi')}手机和电脑连接同一个 Wi-Fi。</span><span>${icon('phone')}扫描电脑上的二维码，用浏览器打开。</span>`}</div><button class="button primary" data-action="retry">重试连接</button><button class="text-button" data-action="help">使用帮助</button>` : ''}</main>`);
      return;
    }
    if (this.role !== state.role) { this.role = state.role; this.shell(state); }
    const admin = state.role === 'admin';
    if (!admin && this.view !== 'settings') this.view = 'shared';
    const settings = this.view === 'settings';
    this.root.querySelector('.app-shell')?.classList.toggle('sidebar-collapsed', this.preferences.collapsed);
    const toggle = element('#sidebar-toggle');
    toggle.setAttribute('aria-expanded', String(!this.preferences.collapsed));
    toggle.setAttribute('aria-label', this.preferences.collapsed ? '展开侧栏' : '收起侧栏');
    toggle.title = this.preferences.collapsed ? '展开侧栏' : '收起侧栏';
    element('#file-content').hidden = settings;
    element('#settings-page').hidden = !settings;
    element('#connection-panel').hidden = settings;
    element('#content-grid').classList.toggle('settings-layout', settings);
    element('#phone-back').hidden = admin || !settings;
    if (settings) renderSettings(element('#settings-page'), state, this.preferences);
    const titles = { shared: admin ? '发送文件' : '电脑文件', received: '收到的文件', activity: '传输记录', settings: '设置' };
    element('#page-title').textContent = titles[this.view];

    element('#page-note').textContent = admin ? (this.view === 'activity' ? '仅保留本次运行的传输记录。' : '') : settings ? '' : `来自${this.preferences.private ? '电脑' : ' ' + state.computer}`;
    element('#page-note').hidden = !element('#page-note').textContent;
    element('#computer-name').textContent = this.preferences.private ? '此电脑' : state.computer;
    element('#nav-count').textContent = String(state.files.length);
    element('#version').textContent = `v${state.version}`;
    element('#add-button').hidden = this.view !== 'shared';
    element<HTMLButtonElement>('#add-button').disabled = admin && Boolean(state.settingsStatus?.protected);
    element('#drop-zone').hidden = !admin || this.view !== 'shared';
    element('#folders-section').hidden = !admin || this.view !== 'shared';
    element('#list-tools').hidden = this.view === 'activity';
    element('#received-path').hidden = this.view !== 'received';
    document.querySelectorAll<HTMLElement>('[data-action="view"]').forEach(button => { button.classList.toggle('active', button.dataset.view === this.view); button.setAttribute('aria-current', button.dataset.view === this.view ? 'page' : 'false'); });
    document.querySelectorAll<HTMLElement>('[data-action="filter"]').forEach(button => { const selected = button.dataset.filter === this.filter; button.classList.toggle('active', selected); button.setAttribute('aria-pressed', String(selected)); });
    const banner = connection.phase === 'reconnecting' ? connection.error : state.warning || (admin && !state.addresses?.length ? '没有检测到局域网地址。请连接 Wi-Fi 后重新打开程序。' : '');
    const warning = element('#network-banner'); warning.hidden = !banner;
    html(warning, `${e(banner)}${state.settingsStatus?.protected ? ' <button class="text-button" data-action="recover-settings">备份并恢复设置</button>' : ''}`);
    const test = element('#test-banner'); test.hidden = !state.testMode; test.textContent = '测试模式：使用合成文件，APK 仅供传输验证。';
    const offline = connection.phase !== 'connected';
    const online = (state.devices ?? []).filter(device => Date.now()/1000 - device.seen < 18).length;
    html(element('#connection-status'), `<i class="${offline ? 'offline' : ''}"></i>${offline ? '连接中断' : admin ? (online ? `${online} 台设备在线` : '等待手机连接') : '已连接电脑'}`);
    element('#privacy-button').setAttribute('aria-pressed', String(this.preferences.private));
    element('#privacy-button').setAttribute('aria-label', this.preferences.private ? '显示连接信息' : '隐藏连接信息');
    html(element('#privacy-button'), icon(this.preferences.private ? 'eye-off' : 'eye'));
    if (admin) element('#transfer-summary').textContent = state.activeTransfers ? `${state.activeTransfers} 个传输任务正在处理` : '';
    if (settings) return;
    if (this.view === 'activity') {
      const history = state.history ?? [];
      element('#list-title').innerHTML = `传输记录 <span class="count">${history.length}</span>`;
      html(element('#files'), history.length ? `<ul class="history-list">${history.map(item => `<li class="history-row"><span class="file-type">${icon(item.direction === 'sent' ? 'send' : 'inbox')}</span><div class="file-name"><strong>${e(item.name)}</strong><span>${item.direction === 'sent' ? '已发送到' : '接收自'} ${e(item.device)} · ${size(item.size)}</span></div><time>${date(item.time)}</time>${icon('check')}</li>`).join('')}</ul>` : `<div class="empty-state"><img src="/assets/cinna-icon.png" alt="" width="86" height="86" /><h3>还没有传输记录</h3><p>手机发送或下载文件后，会显示在这里。</p></div>`);
    } else {
      const data = this.view === 'received' ? state.received ?? [] : state.files;
      element('#list-title').innerHTML = `${this.view === 'received' ? '收到的文件' : admin ? '共享文件' : '可下载文件'} <span class="count">${data.length}</span>`;
      renderFiles(element('#files'), data, { admin, received: this.view === 'received', query: this.query, filter: this.filter });
    }
    if (admin) this.renderComputer(state);
  }
  private shell(state: Snapshot): void {
    const admin = state.role === 'admin'; this.pair = '';
    html(this.root, `<div class="app-shell ${admin ? 'role-admin' : 'role-phone'}"><button class="sidebar-backdrop" data-action="toggle-sidebar" aria-label="收起侧栏"></button><aside class="sidebar" id="sidebar"><div class="sidebar-heading"><a class="brand" href="${admin ? '/desktop' : '/'}"><img src="/assets/cinna-icon.png" alt="LanDrop图标" width="46" height="46" /><span>LanDrop</span></a><button class="icon-button" id="sidebar-toggle" data-action="toggle-sidebar" aria-controls="sidebar" aria-label="收起侧栏">${icon('panel')}</button></div><nav class="nav" aria-label="主导航"><button class="nav-item" data-action="view" data-view="shared" title="发送文件" aria-label="发送文件">${icon('send')}<span>发送文件</span><b id="nav-count">0</b></button><button class="nav-item" data-action="view" data-view="received" title="收到的文件" aria-label="收到的文件">${icon('inbox')}<span>收到的文件</span></button><button class="nav-item" data-action="view" data-view="activity" title="传输记录" aria-label="传输记录">${icon('history')}<span>传输记录</span></button></nav><p class="sidebar-note">${icon('wifi')}手机和电脑需要连接同一个 Wi-Fi。</p><div class="sidebar-bottom"><div class="local-device">${icon('computer')}<strong id="computer-name"></strong></div><button class="quiet-button" data-action="help" title="使用帮助" aria-label="使用帮助">${icon('help')}<span>使用帮助</span></button><button class="quiet-button" data-action="shutdown" title="退出应用" aria-label="退出应用">${icon('power')}<span>退出应用</span></button><button class="quiet-button nav-item" data-action="view" data-view="settings" title="设置" aria-label="设置">${icon('settings')}<span>设置</span></button><small id="version"></small></div></aside><div class="workspace"><header class="topbar"><button class="icon-button sidebar-menu" data-action="toggle-sidebar" aria-label="展开侧栏" aria-controls="sidebar">${icon('menu')}</button><button class="icon-button" id="phone-back" data-action="view" data-view="shared" aria-label="返回文件" hidden>${icon('back')}</button><span class="mobile-brand"><img src="/assets/cinna-icon.png" alt="" width="32" height="32" />LanDrop</span><div class="top-actions"><span class="connection-status" id="connection-status"></span><button class="icon-button" id="privacy-button" data-action="privacy" aria-label="隐藏连接信息">${icon('eye')}</button><button class="icon-button phone-settings" data-action="view" data-view="settings" aria-label="设置">${icon('settings')}</button></div></header><div class="network-banner" id="network-banner" role="status" hidden></div><div class="test-banner" id="test-banner" hidden></div><div class="content-grid" id="content-grid"><main class="primary-column"><div class="page-heading"><div><h1 id="page-title">发送文件</h1><p id="page-note" hidden></p></div><button class="button primary" data-action="add-files" id="add-button">${icon(admin ? 'plus' : 'upload')}${admin ? '添加文件' : '发送文件到电脑'}</button></div><div id="settings-page" class="settings-page" hidden></div><div id="file-content"><section class="drop-zone" id="drop-zone" aria-label="拖入要共享的文件"><span class="drop-icon">${icon('upload')}</span><div><strong>拖入文件</strong><p>支持安装包、图片、文档；单个上传文件最大 8 GB。</p></div></section><section class="file-section" aria-labelledby="list-title"><div class="section-heading"><h2 id="list-title">共享文件</h2><button class="text-button" data-action="refresh">${icon('refresh')}刷新</button></div><div class="list-tools" id="list-tools"><div class="tabs" aria-label="文件类型"><button data-action="filter" data-filter="all" class="tab">全部</button><button data-action="filter" data-filter="apk" class="tab">安装包</button></div><label class="search">${icon('search')}<input id="search-input" type="search" placeholder="搜索文件" aria-label="搜索文件" autocomplete="off" /></label></div><div id="files" class="files"></div></section><section id="folders-section" class="folders-section"><div class="section-heading"><h2>安装包文件夹</h2><button class="text-button" data-action="add-folder">${icon('plus')}添加文件夹</button></div><div id="folders"></div><p class="footnote">自动共享 APK、AAB、APKS 和 XAPK，包含子文件夹。</p></section><div id="received-path" class="received-path" hidden></div></div></main><aside class="connection-panel" id="connection-panel"><div class="pair-card"><div class="section-heading"><h2>扫码连接手机</h2>${icon('phone')}</div><div id="pair-content"></div></div><section class="devices-card"><h2>已连接设备 <span class="count" id="device-count">0</span></h2><div id="devices"></div></section><button class="text-button connection-help" data-action="help">连接帮助 ${icon('arrow')}</button></aside></div><footer class="workspace-footer"><span>${icon('wifi')}局域网传输</span><span>电脑程序需要保持运行。</span><span id="transfer-summary"></span></footer></div></div>`);
    element<HTMLInputElement>('#search-input').value = this.query;
  }
  private renderComputer(state: Snapshot): void {
    const hidden = this.preferences.private;
    const pairKey = `${hidden}|${state.pairUrl}|${state.address}|${state.addresses?.join(',')}`;
    if (pairKey !== this.pair) {
      this.pair = pairKey;
      html(element('#pair-content'), hidden ? `<div class="private-pair"><img src="/assets/cinna-icon.png" alt="" width="96" height="96" /><p>连接信息已隐藏</p><button class="button secondary" data-action="privacy">显示二维码</button></div>` : `<div class="qr-frame">${state.addresses?.length ? `<img src="/api/qr?v=${Date.now()}" width="230" height="230" alt="用手机扫描此二维码连接电脑" />` : '<p>连接 Wi-Fi 后重新打开程序。</p>'}</div><p class="pair-help">手机和电脑连接同一个 Wi-Fi，扫码后用浏览器打开。</p><label class="field-label" for="address-select">电脑地址</label><div class="address-row"><select id="address-select" aria-label="选择局域网地址">${(state.addresses ?? []).map(ip => `<option value="${e(ip)}" ${ip === state.address ? 'selected' : ''}>${e(ip)}:${state.port}</option>`).join('')}</select><button class="icon-button" data-action="copy-link" aria-label="复制手机连接链接">${icon('copy')}</button></div>`);
    }
    const reset = element('#pair-content').parentElement?.querySelector('[data-action="reset-pairs"]');
    if (!reset) element('#pair-content').insertAdjacentHTML('afterend', '<button class="text-button reset-link" data-action="reset-pairs">'+icon('refresh')+'重置连接</button>');
    html(element('#folders'), (state.folders ?? []).length ? (state.folders ?? []).map(folder => `<div class="folder-row"><span class="folder-icon">${icon('folder')}</span><div><strong>${e(folder.name)}</strong><p>${hidden ? '共享路径已隐藏' : e(folder.path)}</p>${folder.error ? `<p class="error-text">${e(folder.error)}</p>` : `<small>${folder.status === 'checking' ? '正在检查安装包…' : folder.count + ' 个安装包 · 自动检查'}</small>`}</div><button class="icon-button" data-action="remove-folder" data-id="${e(folder.id)}" aria-label="移除共享文件夹 ${e(folder.name)}">${icon('close')}</button></div>`).join('') : `<button class="folder-empty" data-action="add-folder">${icon('folder')}添加安装包文件夹${icon('plus')}</button>`);
    html(element('#received-path'), `<div><span>保存位置</span><p>${hidden ? '接收目录路径已隐藏' : e(state.inboxPath)}</p></div><button class="button secondary" data-action="open-inbox">${icon('folder')}打开文件夹</button>`);
    element('#device-count').textContent = String(state.devices?.length ?? 0);
    html(element('#devices'), state.devices?.length ? state.devices.map(device => `<div class="device-row">${icon('phone')}<div><strong>${e(device.name)}</strong><small>${Date.now()/1000-device.seen < 18 ? '在线' : '暂时离线'}${hidden ? '' : ' · '+e(device.peer)}</small></div><button class="icon-button" data-action="revoke" data-id="${e(device.id)}" aria-label="断开 ${e(device.name)}">${icon('close')}</button></div>`).join('') : '<p class="empty-devices">还没有手机连接。</p>');
  }
}
