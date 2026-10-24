import { copyFileSync, cpSync, readFileSync, writeFileSync } from 'node:fs';
const themes = JSON.parse(readFileSync('landrop/ui_theme.json', 'utf8'));
const themeCss = Object.entries(themes).map(([theme, colors]) => {
  const chevron = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${colors.muted}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>`;
  return `${theme === 'light' ? ':root' : ':root[data-theme="dark"]'} { color-scheme:${theme}; ${Object.entries(colors).map(([key, value]) => `--${key}:${value};`).join(' ')} --chevron:url("data:image/svg+xml,${encodeURIComponent(chevron)}"); }`;
}).join('\n');
writeFileSync('landrop/web/assets/theme.css', themeCss + '\n');
copyFileSync('frontend/index.html', 'landrop/web/index.html');
copyFileSync('frontend/style.css', 'landrop/web/assets/style.css');
cpSync('frontend/assets', 'landrop/web/assets', { recursive: true });
console.log('Frontend compiled.');
