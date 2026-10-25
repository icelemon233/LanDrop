import { copyFileSync, cpSync, readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { iconNames } from '../landrop/web/assets/icons.js';
const shell = JSON.parse(readFileSync('landrop/window_shell.json', 'utf8'));
const themes = JSON.parse(readFileSync('landrop/ui_theme.json', 'utf8'));
const themeCss = Object.entries(themes).map(([theme, colors]) => {
  const chevron = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${colors.muted}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>`;
  return `${theme === 'light' ? ':root' : ':root[data-theme="dark"]'} { color-scheme:${theme}; ${Object.entries(colors).map(([key, value]) => `--${key}:${value};`).join(' ')} --chevron:url("data:image/svg+xml,${encodeURIComponent(chevron)}"); }`;
}).join('\n');
const { sidebar, content, controls } = shell;
const variables = {
  'sidebar-expanded': sidebar.expandedWidth, 'sidebar-collapsed': sidebar.collapsedWidth,
  'nav-height': sidebar.rowHeight, 'nav-top': sidebar.topInset, 'nav-inset': sidebar.horizontalInset,
  'nav-icon-column': sidebar.iconColumnWidth, 'icon-size': sidebar.iconSize,
  'sidebar-hide-delay': `${sidebar.hoverHideDelayMs}ms`, 'footer-inset': sidebar.footer.inset,
  'footer-height': sidebar.footer.height, 'footer-gap': sidebar.footer.gap,
  'settings-nav-width': sidebar.footer.settingsExpandedWidth, 'pin-size': sidebar.footer.pinSize,
  'toolbar-height': content.toolbarHeight, 'page-padding': content.pagePadding,
  'page-title-size': content.pageTitleSize, 'section-title-size': content.sectionTitleSize,
  'control-height': controls.height, 'small-radius': controls.radius, radius: controls.panelRadius,
  'settings-field-width': controls.settingsFieldWidth, 'toolbar-padding': content.toolbarHorizontalPadding,
  'status-gap': content.businessStatusGap, 'status-dot-size': content.businessStatusDotSize,
  'body-font-size': content.bodyFontSize, 'auxiliary-font-size': content.auxiliaryFontSize,
  'nav-font-size': sidebar.fontSize, 'nav-font-weight': String(sidebar.fontWeight), 'icon-stroke': String(sidebar.iconStroke),
  'page-title-weight': String(content.pageTitleFontWeight), 'section-title-weight': String(content.sectionTitleFontWeight),
  'section-gap': content.sectionGap, 'label-gap': controls.labelBottomGap,
  'menu-item-height': controls.menuItemHeight, 'menu-inset': controls.menuInset, 'menu-radius': controls.menuRadius,
};
const shellCss = ':root {' + Object.entries(variables).map(([key, value]) => `--${key}:${typeof value === 'number' ? `${value}px` : value};`).join('') + '}';
writeFileSync('landrop/web/assets/theme.css', themeCss + '\n' + shellCss + '\n');
copyFileSync('frontend/index.html', 'landrop/web/index.html');
copyFileSync('frontend/style.css', 'landrop/web/assets/style.css');
cpSync('frontend/assets', 'landrop/web/assets', { recursive: true });
const require = createRequire(import.meta.url);
const lucideRoot = dirname(require.resolve('lucide-static/package.json'));
const symbols = [...new Set(Object.values(iconNames))].sort().map(name => {
  const svg = readFileSync(join(lucideRoot, 'icons', `${name}.svg`), 'utf8');
  const body = svg.match(/<svg\b[^>]*>([\s\S]*?)<\/svg>/)?.[1];
  if (!body) throw new Error(`Invalid Lucide SVG: ${name}`);
  return `<symbol id="${name}" viewBox="0 0 24 24">${body}</symbol>`;
});
writeFileSync('landrop/web/assets/lucide.svg', `<svg xmlns="http://www.w3.org/2000/svg">${symbols.join('')}</svg>\n`);
console.log('Frontend compiled.');
