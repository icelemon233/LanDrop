import { ApiError, createUpload, cancelUpload, uploadStatus, upload } from '../api.js';
import type { UploadStatus } from '../models.js';
import { escape, html, size } from '../ui/dom.js';
import { icon } from '../icons.js';

type Phase = 'queued' | 'starting' | 'sending' | 'saving' | 'done' | 'cancelled' | 'failed' | 'unknown' | 'checking';
interface Task { id: string; name: string; size: number; phase: Phase; percent: number; message: string; file?: File; shared?: boolean; abort?: () => void; requestedCancel?: boolean; created?: boolean; cancellation?: Promise<void> }
const terminal = (task: Task): boolean => ['done','cancelled','failed','unknown'].includes(task.phase);
const id = (): string => Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2,'0')).join('');

export class UploadQueue {
  tasks: Task[] = [];
  private running = false;
  private disposed = false;
  constructor(private target: HTMLElement, private committed: () => Promise<void>, private notify: (message: string, error?: boolean) => void) {
    try {
      const stored: unknown = JSON.parse(sessionStorage.getItem('landrop.upload-tasks.v1') ?? '[]');
      if (Array.isArray(stored)) this.tasks = stored.slice(-100).filter(value => value && typeof value.id === 'string' && /^[a-f0-9]{32}$/.test(value.id) && typeof value.name === 'string' && typeof value.size === 'number' && Number.isFinite(value.size)).map(value => ({ id: value.id, name: value.name, size: value.size, phase: 'unknown', percent: 0, created: true, message: '页面已重新打开，请检查发送结果。' }));
    } catch { /* A damaged task cache never changes saved files. */ }
    this.render();
  }
  add(files: File[]): void {
    if (!files.length) return;
    if (files.length + this.tasks.length > 100) { this.notify('发送列表最多保留 100 个任务，请先清空已结束的任务。', true); return; }
    for (const file of files) this.tasks.push({ id: id(), file, name: file.name, size: file.size, phase: file.size > 8 * 1024**3 ? 'failed' : 'queued', percent: 0, message: file.size > 8 * 1024**3 ? '文件超过 8 GB，请拆分后发送。' : '等待发送' });
    this.render(); void this.process();
  }
  private persist(): void {
    try { sessionStorage.setItem('landrop.upload-tasks.v1', JSON.stringify(this.tasks.filter(task => !['done','cancelled','failed'].includes(task.phase)).map(({id,name,size}) => ({id,name,size})))); } catch { /* Optional recovery storage. */ }
  }
  private apply(task: Task, status: UploadStatus): void {
    task.shared = status.shared;
    task.percent = status.size ? Math.min(100, Math.round(status.received / status.size * 100)) : 0;
    if (status.phase === 'completed') {
      task.phase = 'done'; task.percent = 100;
      task.message = `${status.shared ? '已添加共享' : '已保存到电脑'}${status.savedName !== task.name ? ` · ${status.savedName}` : ''}`;
    } else if (status.phase === 'cancelled') { task.phase = 'cancelled'; task.message = '已取消，文件未保存。'; }
    else if (status.phase === 'failed') { task.phase = 'failed'; task.message = status.error || '发送失败，文件未保存。'; }
    else { task.phase = 'unknown'; task.message = '电脑仍在处理，请稍后检查结果。'; }
  }
  private async reconcile(task: Task): Promise<void> {
    task.phase = 'checking'; task.message = '正在检查电脑上的发送结果…'; this.render();
    try { const status = await uploadStatus(task.id); this.apply(task, status); if (status.phase === 'completed') await this.committed(); }
    catch (error) { task.phase = 'unknown'; task.message = error instanceof ApiError && error.status === 401 ? '连接已失效，请重新连接后查看电脑文件列表。' : '发送结果未确认，请检查电脑文件列表后再决定是否重发。'; }
    this.render();
  }
  async check(identifier: string): Promise<void> { const task = this.tasks.find(item => item.id === identifier); if (task && task.phase === 'unknown') await this.reconcile(task); }
  async cancel(identifier: string): Promise<void> {
    const task = this.tasks.find(item => item.id === identifier); if (!task || terminal(task)) return;
    task.requestedCancel = true; task.abort?.();
    if (task.phase === 'queued') { task.phase = 'cancelled'; task.message = '已取消，文件未发送。'; this.render(); return; }
    if (!task.created) { task.message = '正在取消发送…'; this.render(); return; }
    if (!task.cancellation) task.cancellation = (async () => {
      try { this.apply(task, await cancelUpload(task.id)); if (task.phase === 'done') { task.message += ' · 保存已完成'; await this.committed(); } }
      catch { await this.reconcile(task); }
      this.render();
    })();
    await task.cancellation;
  }
  async cancelAll(): Promise<void> { await Promise.all(this.tasks.filter(task => !terminal(task)).map(task => this.cancel(task.id))); }
  clear(): void { this.tasks = this.tasks.filter(task => !terminal(task)); this.render(); }
  retry(identifier: string): void { const task = this.tasks.find(item => item.id === identifier); if (task?.file && ['failed','cancelled'].includes(task.phase)) this.add([task.file]); }
  private async process(): Promise<void> {
    if (this.running) return; this.running = true;
    try {
      let next: Task | undefined;
      while (!this.disposed && (next = this.tasks.find(task => task.phase === 'queued'))) {
        const task = next;
        task.phase = 'starting'; task.message = '正在建立发送任务…'; this.render();
        try {
          if (!task.file) throw new Error('请重新选择文件。');
          const status = await createUpload(task.id, task.file); task.created = true;
          if (task.requestedCancel || this.disposed) { await this.cancel(task.id); continue; }
          if (status.phase !== 'queued') { this.apply(task, status); continue; }
          task.phase = 'sending'; task.message = '正在发送';
          const operation = upload(task.id, task.file, percent => { if (this.disposed || task.requestedCancel || terminal(task)) return; task.percent = percent; task.phase = percent === 100 ? 'saving' : 'sending'; task.message = percent === 100 ? '正在保存到电脑…' : '正在发送'; this.render(); });
          task.abort = operation.cancel; this.render();
          this.apply(task, await operation.promise); await this.committed();
        } catch (error) {
          if (task.requestedCancel && task.created) await this.cancel(task.id);
          else if (error instanceof ApiError && error.status >= 400 && ![499,502].includes(error.status)) { task.phase = 'failed'; task.message = error.message; }
          else await this.reconcile(task);
        } finally { task.abort = undefined; this.render(); }
      }
    } finally { this.running = false; }
  }
  render(): void {
    this.persist();
    const pending = this.tasks.some(task => !terminal(task));
    html(this.target, this.tasks.length ? `<div class="transfer-heading"><strong>${pending ? '正在发送文件' : '发送结果'}</strong><button class="text-button" data-action="clear-transfers">清空结果</button>${pending ? '<button class="text-button" data-action="cancel-all">取消进行中</button>' : ''}</div><div class="transfer-body">${this.tasks.map(task => `<div class="transfer-item ${task.phase}"><div class="transfer-name"><strong title="${escape(task.name)}">${escape(task.name)}</strong>${!terminal(task) ? `<button class="icon-button" data-action="cancel-upload" data-id="${task.id}" aria-label="取消发送 ${escape(task.name)}">${icon('close')}</button>` : icon(task.phase === 'done' ? 'check' : 'help')}</div><div class="progress-track" role="progressbar" aria-label="${escape(task.name)} 的发送进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${task.percent}"><span style="width:${task.percent}%"></span></div><small>${escape(task.message)}${task.phase === 'sending' ? ` · ${task.percent}%` : ''} · ${size(task.size)}</small>${task.phase === 'unknown' ? `<button class="text-button" data-action="check-upload" data-id="${task.id}">检查结果</button>` : ''}${task.file && ['failed','cancelled'].includes(task.phase) ? `<button class="text-button" data-action="retry-upload" data-id="${task.id}">重新发送</button>` : ''}</div>`).join('')}</div>` : '');
    this.target.classList.toggle('open', this.tasks.length > 0);
  }
  dispose(): void { this.disposed = true; for (const task of this.tasks) task.abort?.(); this.persist(); }
}
