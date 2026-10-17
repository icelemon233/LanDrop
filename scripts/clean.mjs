import { rmSync } from 'node:fs';
import { dirname, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const generated = resolve(root, 'landrop/web');
if (relative(root, generated).replaceAll('\\','/') !== 'landrop/web') throw new Error('Unsafe build output path');
rmSync(generated, { recursive: true, force: true });
