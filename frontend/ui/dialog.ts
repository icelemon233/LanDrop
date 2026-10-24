import { element, escape } from './dom.js';
import { icon } from '../icons.js';

export class Dialogs {
  private generation = 0;
  private confirmAction: (() => Promise<void>) | null = null;
  private returnTo: HTMLElement | null = null;
  private busy = false;
  private pendingFocus: HTMLElement | null = null;
  constructor(private dialog = element<HTMLDialogElement>('#dialog')) {
    dialog.addEventListener('close', () => { if (!dialog.open) { this.confirmAction = null; if (this.returnTo?.isConnected) this.returnTo.focus({ preventScroll: true }); } });
    dialog.addEventListener('cancel', event => { if (this.busy) event.preventDefault(); });
  }
  open(title: string, content: string): number {
    this.generation++; this.confirmAction = null; this.busy = false;
    if (!this.dialog.open) this.returnTo = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (this.dialog.open) this.dialog.close();
    this.dialog.removeAttribute('aria-busy');
    this.dialog.setAttribute('aria-labelledby', 'dialog-title');
    this.dialog.innerHTML = `<div class="dialog-heading"><h2 id="dialog-title">${escape(title)}</h2><button class="icon-button" data-action="close-dialog" aria-label="关闭对话框">${icon('close')}</button></div>${content}<p class="dialog-error" id="dialog-error" role="alert"></p>`;
    this.dialog.showModal(); return this.generation;
  }
  isCurrent(generation: number): boolean { return this.dialog.open && generation === this.generation; }
  close(generation?: number): void { if (generation !== undefined && !this.isCurrent(generation)) return; this.generation++; this.confirmAction = null; this.dialog.close(); }
  error(generation: number, error: unknown): void {
    if (!this.isCurrent(generation)) return;
    const target = this.dialog.querySelector('.dialog-error');
    if (target) target.textContent = error instanceof Error ? error.message : '操作失败，请重试。';
    const input = this.dialog.querySelector('form input');
    input?.setAttribute('aria-invalid', 'true'); input?.setAttribute('aria-describedby', 'dialog-error');
  }
  confirm(title: string, message: string, label: string, callback: () => Promise<void>): void {
    this.open(title, `<p class="dialog-copy">${escape(message)}</p><div class="dialog-actions"><button class="button secondary" data-action="close-dialog">取消</button><button class="button danger" data-action="confirm-dialog">${escape(label)}</button></div>`);
    this.confirmAction = callback;
  }
  async accept(): Promise<void> {
    const callback = this.confirmAction, generation = this.generation;
    if (!callback || this.busy) return;
    this.pending(generation, true);
    try { await callback(); this.close(generation); }
    catch (error) { this.error(generation, error); }
    finally { this.pending(generation, false); }
  }
  current(): number { return this.generation; }
  pending(generation: number, pending: boolean): void {
    if (!this.isCurrent(generation)) return;
    if (pending) this.pendingFocus = document.activeElement instanceof HTMLElement && this.dialog.contains(document.activeElement) ? document.activeElement : null;
    this.busy = pending;
    this.dialog.setAttribute('aria-busy', String(pending));
    this.dialog.querySelectorAll<HTMLInputElement | HTMLButtonElement | HTMLSelectElement>('input,button,select').forEach(control => { control.disabled = pending; });
    if (!pending && (document.activeElement === document.body || document.activeElement === this.dialog) && this.pendingFocus?.isConnected) this.pendingFocus.focus({ preventScroll: true });
  }
}
