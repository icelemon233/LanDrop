/** Semantic aliases; scripts/build.mjs extracts only these official Lucide SVGs. */
export const iconNames = {
  menu: 'menu', back: 'arrow-left', 'chevron-up': 'chevron-up', 'chevron-down': 'chevron-down',
  panel: 'panel-left', eye: 'eye', 'eye-off': 'eye-off', settings: 'settings', send: 'send',
  inbox: 'inbox', history: 'history', computer: 'monitor', phone: 'smartphone', upload: 'upload',
  download: 'download', plus: 'plus', folder: 'folder', file: 'file', apk: 'package', search: 'search',
  copy: 'copy', refresh: 'refresh-cw', close: 'x', check: 'check', arrow: 'arrow-right', wifi: 'wifi',
  help: 'circle-help', power: 'power', trash: 'trash-2', link: 'link', pin: 'pin', 'pin-off': 'pin-off',
  auto: 'monitor', light: 'sun', dark: 'moon',
} as const;

export function icon(name: string, className = ''): string {
  const symbol = iconNames[name as keyof typeof iconNames] ?? iconNames.file;
  return `<svg class="icon ${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><use href="/assets/lucide.svg#${symbol}"></use></svg>`;
}
