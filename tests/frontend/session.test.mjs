import test from 'node:test';
import assert from 'node:assert/strict';
import { SessionController } from '../../landrop/web/assets/session.js';
import { ApiError, parseSnapshot, parseUpload } from '../../landrop/web/assets/api.js';

const snapshot = { role:'phone', computer:'Test computer', files:[], version:'1.1.0', warning:'', testMode:true };
const deferred = () => { let resolve, reject; const promise = new Promise((yes,no) => { resolve=yes; reject=no; }); return {promise,resolve,reject}; };

test('overlapping reads share one result and both callers wait', async () => {
  const pending = deferred(); let calls=0;
  const controller = new SessionController(() => {}, () => { calls++; return pending.promise; });
  const one=controller.refresh(), two=controller.refresh();
  assert.equal(one,two); assert.equal(calls,1);
  pending.resolve(snapshot); await Promise.all([one,two]);
  assert.equal(controller.connection.phase,'connected');
});
test('a mutation discards a read started before the mutation and fetches fresh data', async () => {
  const before = deferred(), after=deferred(), seen=[]; let calls=0;
  const controller=new SessionController(connection => seen.push(connection.snapshot?.computer), () => (++calls===1 ? before.promise : after.promise));
  const original=controller.refresh(), mutation=controller.invalidate();
  before.resolve({...snapshot,computer:'stale'}); await original;
  after.resolve({...snapshot,computer:'fresh'}); await mutation;
  assert.equal(calls,2); assert.equal(controller.connection.snapshot.computer,'fresh'); assert.ok(!seen.includes('stale'));
});
test('responses from the previous connection cannot replace the new connection', async () => {
  const old=deferred(); let calls=0;
  const controller=new SessionController(() => {}, () => ++calls===1 ? old.promise : Promise.resolve({...snapshot,computer:'new'}));
  const initial=controller.refresh(); await controller.connect(async () => {});
  old.resolve({...snapshot,computer:'old'}); await initial;
  assert.equal(controller.connection.snapshot.computer,'new');
});
test('an authentication failure removes cached file data', async () => {
  let rejected=false;
  const controller=new SessionController(() => {}, async () => { if(rejected)throw new ApiError('expired',401); return snapshot; });
  await controller.refresh(); rejected=true; await controller.refresh();
  assert.equal(controller.connection.phase,'unauthorized'); assert.equal(controller.connection.snapshot,null);
});
test('a network failure preserves the current snapshot and reports reconnecting', async () => {
  let rejected=false;
  const controller=new SessionController(() => {}, async () => { if(rejected)throw new ApiError('offline',0); return snapshot; });
  await controller.refresh(); rejected=true; await controller.refresh();
  assert.equal(controller.connection.phase,'reconnecting'); assert.equal(controller.connection.snapshot.computer,'Test computer');
});
test('desktop pages reject a phone session', async () => {
  const controller=new SessionController(() => {}, async () => snapshot, true); await controller.refresh();
  assert.equal(controller.connection.phase,'unauthorized');
});
test('stopping invalidates pending work', async () => {
  const pending=deferred();const controller=new SessionController(() => {}, () => pending.promise);
  const load=controller.refresh();controller.stop();pending.resolve(snapshot);await load;
  assert.equal(controller.connection.phase,'stopped');assert.equal(controller.connection.snapshot,null);
});
test('external response fields are validated at the API boundary', () => {
  assert.deepEqual(parseSnapshot(snapshot),snapshot);
  assert.throws(() => parseSnapshot({...snapshot,files:[{id:'unsafe'}]}),ApiError);
  assert.throws(() => parseSnapshot({...snapshot,role:'admin'}),ApiError);
  assert.throws(() => parseUpload({id:'0'.repeat(32),name:'file',size:5,shared:false,phase:'completed',received:99,savedName:'file',error:''}),ApiError);
});
