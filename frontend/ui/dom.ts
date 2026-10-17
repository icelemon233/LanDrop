export const escape = (value: unknown): string => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char] ?? char));
export function element<T extends HTMLElement = HTMLElement>(selector: string): T {
  const node = document.querySelector<T>(selector);
  if (!node) throw new Error(`Missing element: ${selector}`);
  return node;
}
const rendered = new WeakMap<HTMLElement, string>();
export function html(node: HTMLElement, markup: string): void {
  if (rendered.get(node) !== markup) { node.innerHTML = markup; rendered.set(node, markup); }
}
export function size(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB']; let value = bytes / 1024, index = 0;
  while (value >= 1024 && index < 2) { value /= 1024; index++; }
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[index]}`;
}
export const date = (time: number): string => new Date(time * 1000).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
export async function copy(value: string): Promise<void> {
  if (navigator.clipboard && window.isSecureContext) {
    try { await navigator.clipboard.writeText(value); return; } catch { /* Try the user-initiated browser fallback. */ }
  }
  const textarea = document.createElement('textarea'); textarea.value = value; textarea.className = 'clipboard-helper'; document.body.append(textarea); textarea.select();
  let copied = false;
  try { copied = document.execCommand('copy'); } catch { /* Show a product message below. */ } finally { textarea.remove(); }
  if (!copied) throw new Error('复制失败，请扫描二维码连接。');
}
