import test from 'node:test';
import assert from 'node:assert/strict';
import { trackInputModality } from '../../landrop/web/assets/ui/focus.js';

test('keyboard navigation restores focus hints without modifier or system-shortcut residue', () => {
  const document = new EventTarget();
  document.documentElement = { dataset: {} };
  globalThis.document = document;
  const dispose = trackInputModality();
  const key = (key, modifiers = {}) => {
    const event = new Event('keydown');
    Object.assign(event, { key, altKey:false, ctrlKey:false, metaKey:false, ...modifiers });
    document.dispatchEvent(event);
  };
  for (const name of ['Alt','Control','Shift','Meta']) key(name);
  key('r', { ctrlKey:true }); key('Tab', { altKey:true });
  assert.equal(document.documentElement.dataset.input, 'pointer');
  key('Tab');
  assert.equal(document.documentElement.dataset.input, 'keyboard');
  key('Shift');
  assert.equal(document.documentElement.dataset.input, 'keyboard');
  document.dispatchEvent(new Event('pointerdown'));
  assert.equal(document.documentElement.dataset.input, 'pointer');
  key('ArrowDown');
  assert.equal(document.documentElement.dataset.input, 'keyboard');
  dispose();
});
