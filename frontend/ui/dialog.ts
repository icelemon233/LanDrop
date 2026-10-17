import { element, escape } from './dom.js';
import { icon } from '../icons.js';

export class Dialogs {
  private generation = 0;
  private confirmAction: (() => Promise<void>) | null = null;
  constructor(private dialog = element<HTMLDialogElement>('#dialog')) {
    dialog.addEventListener('close', () => { if (!dialog.open) this.confirmAction = null; });
  }
  open(title: string, content: string): number {
    this.generation++; this.confirmAction = null;
    if (this.dialog.open) this.dialog.close();
    this.dialog.innerHTML = `<div class="dialog-heading"><h2>${escape(title)}</h2><button class="icon-button" data-action="close-dialog" aria-label="关闭对话框">${icon('close')}</button></div>${content}<p class="dialog-error" role="alert"></p>`;
    this.dialog.showModal(); return this.generation;
  }
  isCurrent(generation: number): boolean { return this.dialog.open && generation === this.generation; }
  close(generation?: number): void { if (generation !== undefined && !this.isCurrent(generation)) return; this.generation++; this.confirmAction = null; this.dialog.close(); }
  error(generation: number, error: unknown): void { if (this.isCurrent(generation)) { const target = this.dialog.querySelector('.dialog-error'); if (target) target.textContent = error instanceof Error ? error.message : '操作失败，请重试。'; } }
  confirm(title: string, message: string, label: string, callback: () => Promise<void>): void {
    this.open(title, `<p class="dialog-copy">${escape(message)}</p><div class="dialog-actions"><button class="button secondary" data-action="close-dialog">取消</button><button class="button danger" data-action="confirm-dialog">${escape(label)}</button></div>`);
    this.confirmAction = callback;
  }
  async accept(): Promise<void> { const callback = this.confirmAction; this.close(); if (callback) await callback(); }
  current(): number { return this.generation; }
  pending(generation: number, pending: boolean): void {
    if (!this.isCurrent(generation)) return;
    this.dialog.setAttribute('aria-busy', String(pending));
    this.dialog.querySelectorAll<HTMLInputElement | HTMLButtonElement | HTMLSelectElement>('form input,form button,form select').forEach(control => { control.disabled = pending; });
  }
}
