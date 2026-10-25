import type { Preferences } from './preferences.js';
import { icon } from '../icons.js';

/** Layout state belongs to this shell; only the pin choice is persisted. */
export class Sidebar {
  private sidebar: HTMLElement;
  private pin: HTMLButtonElement;
  private workspace: HTMLElement;
  private menu: HTMLButtonElement;
  private narrow = matchMedia('(max-width: 600px)');
  private pointerInside = false;
  private overlay = false;
  private drawer = false;
  private dragging = false;
  private timer = 0;
  private listeners: (() => void)[] = [];
  private observer: MutationObserver;
  private delay: number;

  constructor(private root: HTMLElement, private preferences: Preferences) {
    this.sidebar = root.querySelector<HTMLElement>('#sidebar')!;
    this.pin = root.querySelector<HTMLButtonElement>('#sidebar-pin')!;
    this.menu = root.querySelector<HTMLButtonElement>('.sidebar-menu')!;
    this.workspace = root.querySelector<HTMLElement>('.workspace')!;
    this.delay = Number.parseFloat(getComputedStyle(root).getPropertyValue('--sidebar-hide-delay'));
    this.listen(this.sidebar, 'pointerenter', event => {
      if ((event as PointerEvent).pointerType === 'touch') return;
      this.pointerInside = true; this.cancelHide(); this.overlay = true; this.refresh();
    });
    this.listen(this.sidebar, 'pointerleave', () => { this.pointerInside = false; this.scheduleHide(); });
    this.listen(this.sidebar, 'focusin', () => {
      if (this.keyboardFocus()) { this.cancelHide(); this.overlay = true; this.refresh(); }
    });
    this.listen(this.sidebar, 'focusout', () => this.scheduleHide());
    this.listen(document, 'input-modality-change', () => {
      if (this.keyboardFocus()) { this.overlay = true; this.refresh(); }
      else this.scheduleHide();
    });
    this.listen(this.sidebar, 'dragenter', () => { this.dragging = true; this.overlay = true; this.cancelHide(); this.refresh(); });
    this.listen(this.sidebar, 'dragleave', event => {
      if (!this.sidebar.contains((event as DragEvent).relatedTarget as Node | null)) { this.dragging = false; this.scheduleHide(); }
    });
    for (const name of ['drop','dragend']) this.listen(document, name, () => { this.dragging = false; this.scheduleHide(); });
    this.listen(this.root, 'keydown', event => this.keydown(event as KeyboardEvent));
    this.listen(this.narrow, 'change', () => { this.drawer = false; this.overlay = false; this.refresh(); });
    this.observer = new MutationObserver(() => this.scheduleHide());
    this.observer.observe(this.sidebar, { subtree: true, attributes: true, attributeFilter: ['aria-expanded','aria-haspopup'] });
    this.refresh();
  }

  private listen(target: EventTarget, name: string, listener: EventListener): void {
    target.addEventListener(name, listener);
    this.listeners.push(() => target.removeEventListener(name, listener));
  }
  private keyboardFocus(): boolean {
    const active = document.activeElement;
    return document.documentElement.dataset.input === 'keyboard' && active instanceof HTMLElement && this.sidebar.contains(active) && active.matches(':focus-visible');
  }
  private menuOpen(): boolean { return Boolean(this.sidebar.querySelector('[aria-haspopup][aria-expanded="true"]')); }
  private cancelHide(): void { clearTimeout(this.timer); }
  private scheduleHide(): void {
    this.cancelHide();
    this.timer = window.setTimeout(() => {
      if (this.pointerInside || this.keyboardFocus() || this.menuOpen() || this.dragging) return;
      this.overlay = false; this.refresh();
    }, this.delay);
  }
  togglePin(): void {
    this.cancelHide();
    this.overlay = this.pointerInside || this.keyboardFocus();
    this.preferences.togglePinned();
    this.refresh();
  }
  toggleDrawer(): void {
    this.drawer = !this.drawer; this.refresh();
    if (this.drawer) this.sidebar.querySelector<HTMLButtonElement>('.nav-item')?.focus();
  }
  closeDrawer(returnFocus = true): void {
    if (!this.drawer) return;
    this.drawer = false; this.refresh();
    if (returnFocus) this.menu.focus();
  }
  private keydown(event: KeyboardEvent): void {
    if (!this.narrow.matches || !this.drawer) return;
    if (event.key === 'Escape') { event.preventDefault(); this.closeDrawer(); }
    if (event.key === 'Tab') {
      const controls = [...this.sidebar.querySelectorAll<HTMLElement>('button:not([disabled]),a[href]')].filter(node => node.getClientRects().length);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  }
  refresh(): void {
    const narrow = this.narrow.matches;
    const expanded = narrow ? this.drawer : this.preferences.pinned || this.overlay;
    this.root.classList.toggle('sidebar-unpinned', !this.preferences.pinned);
    this.root.classList.toggle('sidebar-overlay', !narrow && !this.preferences.pinned && expanded);
    this.root.classList.toggle('drawer-open', narrow && this.drawer);
    this.sidebar.dataset.expanded = String(expanded);
    this.menu.setAttribute('aria-expanded', String(narrow && this.drawer));
    this.pin.setAttribute('aria-pressed', String(this.preferences.pinned));
    const label = this.preferences.pinned ? '取消固定侧栏' : '固定侧栏';
    this.pin.setAttribute('aria-label', label); this.pin.title = label;
    const name = this.preferences.pinned ? 'pin-off' : 'pin';
    if (this.pin.dataset.icon !== name) { this.pin.innerHTML = icon(name); this.pin.dataset.icon = name; }
    if ((!expanded || narrow) && this.pin.contains(document.activeElement)) this.sidebar.querySelector<HTMLButtonElement>('.settings-nav')?.focus({ preventScroll: true });
    this.workspace.inert = narrow && this.drawer;
    this.sidebar.inert = narrow && !this.drawer;
  }
  dispose(): void { this.cancelHide(); this.observer.disconnect(); this.listeners.forEach(dispose => dispose()); }
}
