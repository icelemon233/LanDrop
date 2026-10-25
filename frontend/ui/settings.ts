import type { Snapshot } from '../models.js';
import type { Preferences } from './preferences.js';
import { escape as e, html } from './dom.js';
import { icon } from '../icons.js';

export function renderSettings(target: HTMLElement, state: Snapshot, preferences: Preferences): void {
  if (!target.dataset.ready) {
    html(target, `<section class="settings-section" aria-labelledby="appearance-heading"><h2 id="appearance-heading">外观</h2><label class="field-label" for="theme-select">主题</label><div class="field-select-wrap"><span class="field-icon" id="theme-icon">${icon(preferences.theme)}</span><select id="theme-select" name="theme" class="with-icon"><option value="auto">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option></select></div></section><section class="settings-section" id="window-settings" hidden aria-labelledby="window-heading"><h2 id="window-heading">窗口与退出</h2><label class="field-label" for="close-behavior">关闭窗口时</label><div class="field-select-wrap"><select id="close-behavior" class="path-input"><option value="tray">进入托盘</option><option value="exit">退出应用</option></select></div><p class="field-help" id="close-help">最小化保留在任务栏。进入托盘后，连接和传输继续。</p><p id="window-feedback" class="field-help" role="status"></p></section>${state.role === 'admin' ? `<section class="settings-section" aria-labelledby="computer-heading"><h2 id="computer-heading">电脑</h2><form id="name-form"><label class="field-label" for="computer-display-name">电脑名称</label><div class="setting-input-row"><input id="computer-display-name" class="path-input" value="${e(state.computer)}" maxlength="64" required aria-describedby="name-feedback" /><button class="button secondary" type="submit">保存名称</button></div><p id="name-feedback" class="field-help" role="status"></p></form></section>` : ''}<section class="settings-section settings-about"><h2>关于</h2><p>LanDrop <span class="settings-version">v${e(state.version)}</span></p><p class="field-help">开发者 Cinna</p><p class="field-help">局域网文件传输</p><button class="button secondary" data-action="help">使用帮助</button></section>`);
    target.dataset.ready = 'true';
  }
  const theme = target.querySelector<HTMLSelectElement>('#theme-select');
  if (theme) theme.value = preferences.theme;
  const themeIcon = target.querySelector<HTMLElement>('#theme-icon');
  if (themeIcon) html(themeIcon, icon(preferences.theme));
  const windowSettings = target.querySelector<HTMLElement>('#window-settings');
  if (windowSettings) windowSettings.hidden = !state.desktop;
  const close = target.querySelector<HTMLSelectElement>('#close-behavior');
  if (close && state.desktop && document.activeElement !== close) close.value = state.desktop.closeBehavior;
  const help = target.querySelector<HTMLElement>('#close-help');
  if (help && state.desktop) help.textContent = state.desktop.trayAvailable ? '最小化保留在任务栏。进入托盘后，连接和传输继续。' : '托盘暂不可用，关闭时将保留在任务栏。可以从应用中退出。';
}
