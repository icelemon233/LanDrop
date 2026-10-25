import { icon } from '../icons.js';

type ValueChange = (select: HTMLSelectElement, value: string) => void;
type OptionData = Pick<HTMLOptionElement, 'value' | 'text' | 'label' | 'disabled'>;

/** The displayed menu and a later click must refer to the same option values. */
export class SelectOptions {
  readonly signature: string;
  private values: string[];
  constructor(options: ArrayLike<OptionData>) {
    const entries = [...Array.from(options)].map(({ value, text, label, disabled }) => ({ value, text, label, disabled }));
    this.signature = JSON.stringify(entries); this.values = entries.map(option => option.value);
  }
  valueAt(index: number, current: ArrayLike<OptionData>): string | undefined {
    if (new SelectOptions(current).signature !== this.signature) return undefined;
    return this.values[index];
  }
}

/** Native values/form association remain intact; the enhanced popup is shared. */
class SelectControl {
  readonly wrapper = document.createElement('div');
  readonly trigger = document.createElement('button');
  private popup = document.createElement('div');
  private active = 0;
  private open = false;
  private listeners: (() => void)[] = [];
  private search = '';
  private searchedAt = 0;
  private signature = '';
  private restoreFocus = false;
  private displayed?: SelectOptions;
  private observer: MutationObserver;

  constructor(readonly select: HTMLSelectElement, private changed: ValueChange, identifier: number) {
    this.wrapper.className = 'select-control';
    select.before(this.wrapper); this.wrapper.append(select, this.trigger);
    this.trigger.type = 'button'; this.trigger.className = 'select-trigger';
    this.trigger.id = `${select.id || 'select'}-trigger-${identifier}`;
    this.trigger.setAttribute('role', 'combobox');
    this.trigger.setAttribute('aria-haspopup', 'listbox');
    this.trigger.setAttribute('aria-expanded', 'false');
    this.popup.className = 'select-menu'; this.popup.id = `${this.trigger.id}-options`;
    this.popup.setAttribute('role', 'listbox');
    this.trigger.setAttribute('aria-controls', this.popup.id);
    const labels = [...select.labels ?? []];
    if (labels.length) {
      labels.forEach((label, index) => {
        label.id ||= `${this.trigger.id}-label-${index}`;
        this.listen(label, 'click', event => { event.preventDefault(); this.trigger.focus(); });
      });
      this.trigger.setAttribute('aria-labelledby', labels.map(label => label.id).join(' '));
      this.popup.setAttribute('aria-labelledby', labels.map(label => label.id).join(' '));
    } else this.trigger.setAttribute('aria-label', select.getAttribute('aria-label') ?? '选择');
    if (select.getAttribute('aria-describedby')) this.trigger.setAttribute('aria-describedby', select.getAttribute('aria-describedby')!);
    this.listen(this.trigger, 'click', () => this.open ? this.close() : this.show());
    this.listen(this.trigger, 'keydown', event => this.keydown(event as KeyboardEvent));
    this.listen(this.popup, 'pointermove', event => {
      const item = (event.target as Element).closest<HTMLElement>('[data-option]');
      if (item) this.setActive(Number(item.dataset.option));
    });
    this.listen(this.popup, 'pointerdown', event => event.preventDefault()); // Keep the combobox's real focus.
    this.listen(this.popup, 'click', event => {
      const item = (event.target as Element).closest<HTMLElement>('[data-option]');
      if (item) this.accept(Number(item.dataset.option));
    });
    this.listen(document, 'pointerdown', event => {
      if (!this.wrapper.contains(event.target as Node) && !this.popup.contains(event.target as Node)) { this.restoreFocus = false; this.close(false); }
    }, true);
    this.listen(document, 'scroll', event => { if (!this.popup.contains(event.target as Node)) this.close(false); }, true);
    this.listen(window, 'resize', () => this.close(false));
    this.listen(select, 'invalid', event => { event.preventDefault(); this.trigger.focus(); });
    this.observer = new MutationObserver(() => this.sync());
    this.observer.observe(select, { childList:true, subtree:true, characterData:true, attributes:true, attributeFilter:['value','label','disabled','selected'] });
    this.sync();
    select.classList.add('select-native'); select.tabIndex = -1; select.setAttribute('aria-hidden', 'true');
  }

  private listen(target: EventTarget, name: string, listener: EventListener, capture = false): void {
    target.addEventListener(name, listener, capture);
    this.listeners.push(() => target.removeEventListener(name, listener, capture));
  }
  sync(): void {
    const select = this.select, option = select.selectedOptions[0];
    if (select.disabled && !this.trigger.disabled && document.activeElement === this.trigger) this.restoreFocus = true;
    this.trigger.disabled = select.disabled;
    if (!select.disabled && this.restoreFocus) {
      this.restoreFocus = false;
      if (document.activeElement === document.body) this.trigger.focus({ preventScroll:true });
    }
    this.trigger.classList.toggle('with-icon', select.classList.contains('with-icon'));
    const signature = `${select.value}|${new SelectOptions(select.options).signature}|${select.disabled}`;
    if (signature !== this.signature) {
      this.close(false);
      this.signature = signature;
      const text = document.createElement('span'); text.className = 'select-value'; text.textContent = option?.label ?? '';
      const arrow = document.createElement('span'); arrow.className = 'select-chevron'; arrow.innerHTML = icon('chevron-down');
      this.trigger.replaceChildren(text, arrow);
    }
    if (select.disabled) this.close(false);
  }
  private options(): HTMLOptionElement[] { return [...this.select.options]; }
  private show(): void {
    if (this.select.disabled || this.open) return;
    this.open = true; this.active = Math.max(0, this.select.selectedIndex);
    this.displayed = new SelectOptions(this.select.options);
    this.popup.replaceChildren(...this.options().map((option, index) => {
      const item = document.createElement('div');
      item.id = `${this.popup.id}-${index}`; item.className = 'select-option'; item.dataset.option = String(index);
      item.setAttribute('role', 'option'); item.setAttribute('aria-selected', String(option.selected));
      item.setAttribute('aria-disabled', String(option.disabled));
      if (this.select.name === 'theme') { const graphic = document.createElement('span'); graphic.innerHTML = icon(option.value); item.append(graphic); }
      const text = document.createElement('span'); text.className = 'option-label'; text.textContent = option.label; item.append(text);
      if (option.selected) { const check = document.createElement('span'); check.className = 'option-check'; check.innerHTML = icon('check'); item.append(check); }
      return item;
    }));
    document.body.append(this.popup);
    this.trigger.setAttribute('aria-expanded', 'true');
    this.position(); this.setActive(this.active);
  }
  private position(): void {
    const rect = this.trigger.getBoundingClientRect();
    const availableBelow = innerHeight - rect.bottom - 14, availableAbove = rect.top - 14;
    const desired = Math.min(320, this.popup.scrollHeight);
    const above = availableBelow < desired && availableAbove > availableBelow;
    const rowHeight = Number.parseFloat(getComputedStyle(this.popup).getPropertyValue('--menu-item-height'));
    this.popup.style.maxHeight = `${Math.max(rowHeight, Math.min(320, above ? availableAbove : availableBelow))}px`;
    const width = Math.min(Math.max(rect.width, 160), innerWidth - 16);
    this.popup.style.width = `${width}px`;
    this.popup.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - width - 8))}px`;
    this.popup.style.top = `${above ? Math.max(8, rect.top - this.popup.getBoundingClientRect().height - 6) : rect.bottom + 6}px`;
  }
  private setActive(index: number): void {
    if (this.options()[index]?.disabled) return;
    this.active = index;
    this.popup.querySelectorAll<HTMLElement>('[data-option]').forEach((item, i) => item.classList.toggle('option-active', i === index));
    const item = this.popup.querySelector<HTMLElement>(`[data-option="${index}"]`);
    if (item) { this.trigger.setAttribute('aria-activedescendant', item.id); item.scrollIntoView({ block: 'nearest' }); }
  }
  private accept(index: number): void {
    const value = this.displayed?.valueAt(index, this.select.options);
    if (value === undefined) { this.close(); this.sync(); return; }
    const option = this.options().find(option => option.value === value); if (!option || option.disabled) return;
    const previous = this.select.value;
    this.select.value = option.value; this.sync(); this.close();
    if (previous !== option.value) this.changed(this.select, option.value);
  }
  private keydown(event: KeyboardEvent): void {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const options = this.options();
    if (event.key === 'Tab') { this.close(false); return; }
    if (event.key === 'Escape') { if (this.open) { event.preventDefault(); this.close(); } return; }
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (this.open) this.accept(this.active); else this.show(); return; }
    if (['ArrowDown','ArrowUp','Home','End'].includes(event.key)) {
      event.preventDefault();
      if (!this.open) { this.show(); return; }
      const step = event.key === 'ArrowUp' || event.key === 'End' ? -1 : 1;
      let next = event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1 : (this.active + step + options.length) % options.length;
      for (let i = 0; i < options.length && options[next]?.disabled; i++) next = (next + step + options.length) % options.length;
      this.setActive(next); return;
    }
    if (event.key.length === 1) {
      event.preventDefault();
      if (performance.now() - this.searchedAt > 1000) this.search = '';
      this.searchedAt = performance.now(); this.search += event.key.toLocaleLowerCase();
      this.show();
      const index = options.findIndex(option => !option.disabled && option.label.toLocaleLowerCase().startsWith(this.search));
      if (index >= 0) this.setActive(index);
    }
  }
  close(returnFocus = true): void {
    if (!this.open) return;
    this.open = false; this.popup.remove();
    this.trigger.setAttribute('aria-expanded', 'false'); this.trigger.removeAttribute('aria-activedescendant');
    if (returnFocus && this.trigger.isConnected) this.trigger.focus({ preventScroll: true });
  }
  dispose(): void { this.close(false); this.observer.disconnect(); this.listeners.forEach(dispose => dispose()); }
}

export class Selects {
  private controls = new Map<HTMLSelectElement, SelectControl>();
  private nextId = 0;
  constructor(private changed: ValueChange) {}
  refresh(): void {
    for (const [select, control] of this.controls) if (!select.isConnected) { control.dispose(); this.controls.delete(select); }
    document.querySelectorAll<HTMLSelectElement>('select').forEach(select => {
      let control = this.controls.get(select);
      if (!control) { control = new SelectControl(select, this.changed, this.nextId++); this.controls.set(select, control); }
      control.sync();
    });
  }
  dispose(): void { this.controls.forEach(control => control.dispose()); this.controls.clear(); }
}
