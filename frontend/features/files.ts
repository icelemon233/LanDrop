import type { SharedFile } from '../models.js';
import { escape as e, html, size, date } from '../ui/dom.js';
import { icon } from '../icons.js';

export const installers = new Set(['.apk','.aab','.apks','.xapk']);
export function renderFiles(target: HTMLElement, files: SharedFile[], options: { admin: boolean; received: boolean; query: string; filter: string }): void {
  const filtered = files.filter(file => (options.filter !== 'apk' || installers.has(file.extension)) && file.name.toLocaleLowerCase().includes(options.query.toLocaleLowerCase()));
  if (!filtered.length) {
    const searching = Boolean(options.query) || (options.filter === 'apk' && files.length > 0);
    html(target, `<div class="empty-state"><img src="/assets/cinna-icon.png" alt="" width="86" height="86" /><h3>${searching ? '没有找到匹配的文件' : options.received ? '还没有收到文件' : options.admin ? '还没有添加文件' : '电脑还没有共享文件'}</h3><p>${searching ? '试试其他关键词，或切换到全部文件。' : options.received ? '在手机页面选择「发送文件到电脑」。' : options.admin ? '选择文件，或添加项目的安装包输出文件夹。' : '在电脑端添加文件后，这里会自动更新。'}</p>${!searching && options.admin && !options.received ? '<button class="text-button" data-action="add-folder">添加安装包文件夹 '+icon('arrow')+'</button>' : ''}</div>`); return;
  }
  const newest = files.find(file => installers.has(file.extension))?.id;
  html(target, `<div class="file-table-heading"><span>文件名称</span><span>大小</span><span>更新于</span><span class="sr-only">操作</span></div><ul class="file-list">${filtered.map(file => `<li class="file-row"><span class="file-type ${installers.has(file.extension) ? 'type-apk' : ''}">${icon(installers.has(file.extension) ? 'apk' : 'file')}</span><div class="file-name"><strong>${e(file.name)}</strong><span>${e(file.source)}${file.id === newest && !options.received ? '<b class="latest-label">最新安装包</b>' : ''}</span></div><span class="file-size">${size(file.size)}</span><time class="file-date">${date(file.modified)}</time><div class="file-actions"><a class="icon-button download-button" href="/download/${file.id}${options.received ? '?received=1' : ''}" data-action="download" download aria-label="下载 ${e(file.name)}" title="下载文件">${icon('download')}</a>${options.admin && !options.received ? `<button class="icon-button remove-button" data-action="remove-file" data-id="${file.id}" aria-label="取消共享 ${e(file.name)}" title="取消共享，保留原文件">${icon('close')}</button>` : ''}</div></li>`).join('')}</ul>`);
}
