import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { Preferences } from '../../landrop/web/assets/ui/preferences.js';

function environment(saved = {}, dark = false) {
  const values = new Map(Object.entries(saved));
  const root = { dataset: {} }, meta = {};
  const media = new Map();
  globalThis.localStorage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  globalThis.document = { documentElement: root, querySelector: () => ({ setAttribute: (key, value) => { meta[key] = value; } }) };
  globalThis.getComputedStyle = () => ({ getPropertyValue: () => root.dataset.theme === 'dark' ? '#1B1D20' : '#FFFCF6' });
  globalThis.matchMedia = query => {
    if (!media.has(query)) media.set(query, { matches: query.includes('color-scheme') ? dark : false, addEventListener(_type, listener) { this.listener = listener; }, removeEventListener() { this.listener = null; } });
    return media.get(query);
  };
  return { values, root, meta, media };
}

test('saved appearance is applied by the blocking bootstrap and retained on application handoff', () => {
  const env = environment({ 'landrop.theme': 'light' }, true);
  const bootstrap = readFileSync(new URL('../../landrop/web/assets/appearance.js', import.meta.url), 'utf8');
  vm.runInNewContext(bootstrap, { document, localStorage, matchMedia });
  assert.equal(env.root.dataset.theme, 'light');
  const preferences = new Preferences(() => {});
  assert.equal(env.root.dataset.theme, 'light');
  preferences.dispose();
});

test('system changes follow auto mode while manual choice and privacy survive reopening', () => {
  const env = environment(); let changes = 0;
  const preferences = new Preferences(() => { changes++; });
  const color = env.media.get('(prefers-color-scheme: dark)');
  color.matches = true; color.listener();
  assert.equal(env.root.dataset.theme, 'dark');
  preferences.setTheme('light');
  color.listener();
  assert.equal(env.root.dataset.theme, 'light');
  preferences.togglePrivacy();
  preferences.togglePinned();
  const restored = new Preferences(() => {});
  assert.equal(restored.theme, 'light'); assert.equal(restored.private, true); assert.equal(restored.pinned, false);
  assert.ok(changes >= 4);
  restored.dispose(); preferences.dispose();
});

test('the explicit old sidebar preference migrates and only a new pin choice is written', () => {
  const env = environment({ 'landrop.sidebar-collapsed': 'true' });
  const preferences = new Preferences(() => {});
  assert.equal(preferences.pinned, false);
  preferences.togglePinned();
  assert.equal(env.values.get('landrop.sidebar-pinned'), 'true');
  assert.equal(env.values.get('landrop.sidebar-collapsed'), 'true');
  assert.equal([...env.values.keys()].some(key => /hover|drawer/.test(key)), false);
  preferences.dispose();
});

test('appearance remains usable when device storage is unavailable', () => {
  const env = environment();
  globalThis.localStorage = { getItem() { throw Error('blocked'); }, setItem() { throw Error('blocked'); } };
  const preferences = new Preferences(() => {});
  preferences.setTheme('dark');
  assert.equal(env.root.dataset.theme, 'dark');
  assert.equal(env.meta.content, '#1B1D20');
  preferences.dispose();
});

test('a desktop theme survives an origin or port change before both first paint and handoff', () => {
  const env = environment({ 'landrop.theme': 'light' });
  env.root.dataset.windowTheme = 'dark';
  const bootstrap = readFileSync(new URL('../../landrop/web/assets/appearance.js', import.meta.url), 'utf8');
  vm.runInNewContext(bootstrap, { document, localStorage, matchMedia });
  assert.equal(env.root.dataset.theme, 'dark');
  const preferences = new Preferences(() => {});
  assert.equal(preferences.theme, 'dark');
  assert.equal(env.root.dataset.theme, 'dark');
  preferences.dispose();
});
