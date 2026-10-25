import test from 'node:test';
import assert from 'node:assert/strict';
import { SelectOptions } from '../../landrop/web/assets/ui/select.js';

const option = (value, text = value, disabled = false) => ({ value, text, disabled });
test('an open address menu never commits a different address after live option changes', () => {
  const displayed = new SelectOptions([option('192.168.1.2'), option('10.0.0.2')]);
  assert.equal(displayed.valueAt(1, [option('192.168.1.2'), option('10.0.0.2')]), '10.0.0.2');
  assert.equal(displayed.valueAt(1, [option('10.0.0.2'), option('192.168.1.2')]), undefined);
  assert.equal(displayed.valueAt(1, [option('192.168.1.2')]), undefined);
  assert.equal(displayed.valueAt(1, [option('192.168.1.2'), option('10.0.0.2','Wi-Fi',true)]), undefined);
  assert.equal(displayed.valueAt(1, [option('192.168.1.2'), option('10.0.0.2','New label')]), undefined);
});
