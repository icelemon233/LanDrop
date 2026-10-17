import { copyFileSync, cpSync } from 'node:fs';
copyFileSync('frontend/index.html', 'landrop/web/index.html');
copyFileSync('frontend/style.css', 'landrop/web/assets/style.css');
cpSync('frontend/assets', 'landrop/web/assets', { recursive: true });
console.log('Frontend compiled.');
