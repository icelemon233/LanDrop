export type Theme = 'auto' | 'light' | 'dark';
function read(key: string): string | null { try { return localStorage.getItem(key); } catch { return null; } }
function write(key: string, value: string): void { try { localStorage.setItem(key, value); } catch { /* The current choice still applies when storage is unavailable. */ } }
export class Preferences {
  theme: Theme;
  private = read('landrop.hide-connection') === 'true';
  collapsed = read('landrop.sidebar-collapsed') === 'true' || (read('landrop.sidebar-collapsed') === null && matchMedia('(max-width: 1100px)').matches);
  private media = matchMedia('(prefers-color-scheme: dark)');
  private narrow = matchMedia('(max-width: 1100px)');
  private resized = (): void => { if (read('landrop.sidebar-collapsed') === null) { this.collapsed = this.narrow.matches; this.notify(); } };
  private changed = (): void => { this.apply(); this.notify(); };
  constructor(private notify: () => void) {
    const saved = document.documentElement.dataset.windowTheme ?? read('landrop.theme'); this.theme = saved === 'light' || saved === 'dark' ? saved : 'auto';
    this.media.addEventListener('change', this.changed); this.narrow.addEventListener('change', this.resized); this.apply();
  }
  get resolved(): 'dark' | 'light' { return this.theme === 'auto' ? (this.media.matches ? 'dark' : 'light') : this.theme; }
  apply(): void { document.documentElement.dataset.theme = this.resolved; document.querySelector('meta[name="theme-color"]')?.setAttribute('content', getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim()); }
  setTheme(theme: string): void { if (!['auto','light','dark'].includes(theme)) return; this.theme = theme as Theme; write('landrop.theme', theme); this.apply(); this.notify(); }
  togglePrivacy(): void { this.private = !this.private; write('landrop.hide-connection', String(this.private)); this.notify(); }
  toggleSidebar(): void { this.collapsed = !this.collapsed; write('landrop.sidebar-collapsed', String(this.collapsed)); this.notify(); }
  dispose(): void { this.media.removeEventListener('change', this.changed); this.narrow.removeEventListener('change', this.resized); }
}
