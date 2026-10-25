export type Theme = 'auto' | 'light' | 'dark';
function read(key: string): string | null { try { return localStorage.getItem(key); } catch { return null; } }
function write(key: string, value: string): void { try { localStorage.setItem(key, value); } catch { /* The current choice still applies when storage is unavailable. */ } }
export class Preferences {
  theme: Theme;
  private = read('landrop.hide-connection') === 'true';
  // Migrate the previous explicit choice; hover and drawer state stay transient.
  pinned = read('landrop.sidebar-pinned') !== null ? read('landrop.sidebar-pinned') !== 'false' : read('landrop.sidebar-collapsed') !== 'true';
  private media = matchMedia('(prefers-color-scheme: dark)');
  private changed = (): void => { this.apply(); this.notify(); };
  constructor(private notify: () => void) {
    const saved = document.documentElement.dataset.windowTheme ?? read('landrop.theme'); this.theme = saved === 'light' || saved === 'dark' ? saved : 'auto';
    this.media.addEventListener('change', this.changed); this.apply();
  }
  get resolved(): 'dark' | 'light' { return this.theme === 'auto' ? (this.media.matches ? 'dark' : 'light') : this.theme; }
  apply(): void { document.documentElement.dataset.theme = this.resolved; document.querySelector('meta[name="theme-color"]')?.setAttribute('content', getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim()); }
  setTheme(theme: string): void { if (!['auto','light','dark'].includes(theme)) return; this.theme = theme as Theme; write('landrop.theme', theme); this.apply(); this.notify(); }
  togglePrivacy(): void { this.private = !this.private; write('landrop.hide-connection', String(this.private)); this.notify(); }
  togglePinned(): void { this.pinned = !this.pinned; write('landrop.sidebar-pinned', String(this.pinned)); this.notify(); }
  dispose(): void { this.media.removeEventListener('change', this.changed); }
}
