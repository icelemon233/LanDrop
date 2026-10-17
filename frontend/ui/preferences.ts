export type Theme = 'auto' | 'light' | 'dark';
function read(key: string): string | null { try { return localStorage.getItem(key); } catch { return null; } }
function write(key: string, value: string): void { try { localStorage.setItem(key, value); } catch { /* The current choice still applies when storage is unavailable. */ } }
export class Preferences {
  theme: Theme;
  private = read('landrop.hide-connection') === 'true';
  private media = matchMedia('(prefers-color-scheme: dark)');
  private changed = (): void => this.apply();
  constructor(private notify: () => void) {
    const saved = read('landrop.theme'); this.theme = saved === 'light' || saved === 'dark' ? saved : 'auto';
    this.media.addEventListener('change', this.changed); this.apply();
  }
  apply(): void { document.documentElement.dataset.theme = this.theme === 'auto' ? (this.media.matches ? 'dark' : 'light') : this.theme; }
  setTheme(theme: string): void { if (!['auto','light','dark'].includes(theme)) return; this.theme = theme as Theme; write('landrop.theme', theme); this.apply(); this.notify(); }
  togglePrivacy(): void { this.private = !this.private; write('landrop.hide-connection', String(this.private)); this.notify(); }
  dispose(): void { this.media.removeEventListener('change', this.changed); }
}
