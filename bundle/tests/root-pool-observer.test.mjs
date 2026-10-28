// Synthetic offline fixtures only. No SDK import, Host, model or desktop run.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRootPoolObserver, SOURCE_PIN, verifyRuntimeSource, resolveRuntimePackageUrls } from '../src/root-pool-observer.mjs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';
import { capacityOf, createPermitLedger, hash } from '../src/runtime-guard-core.mjs';

function fixture({limit=8}={}) {
  const root={id:'root'},second={id:'other-root'},live=new Map([[root.id,root],[second.id,second]]),owners=new Map(),roots=[root,second];
  const registry={get:id=>live.get(id),roots:()=>roots.slice(),isOwnedBy:(id,parent)=>owners.get(id)===parent};
  const manager={ctx:{agents:registry},rootPools:new WeakMap(),resident:new Map(),materializations:new Set(),closingScopes:new Map(),draining:false,
    rootPool:()=>assert.fail('read-only observer must not create a pool'),materialize:()=>assert.fail('must not reconstruct')};
  const ctx={agents:registry,subagents:{manager,config:{maxActiveSubagents:{get:()=>limit}},startActivation:()=>assert.fail('must not spawn')}};
  const source={pin:SOURCE_PIN,checkCurrent:()=>{},checkPool:()=>{}};
  let time=100000;
  const observer=createRootPoolObserver({verifySource:async()=>source,now:()=>time});
  const poolFor=agent=>{const pool={slots:new Set(),reserve:()=>assert.fail('must not reserve')};manager.rootPools.set(agent,pool);return pool;};
  const add=(parent,pool,id,{kind='local',closing=false}={})=>{
    const agent={id},slot=Symbol(id);pool.slots.add(slot);live.set(id,agent);owners.set(id,parent);
    const activation={pool,childId:id,kind,parent,ancestry:new WeakSet([root,parent,agent]),handle:{agent},closing:closing?Promise.resolve():undefined};manager.resident.set(id,activation);
    return {agent,activation,slot,release:()=>{manager.resident.delete(id);pool.slots.delete(slot);live.delete(id);owners.delete(id);}};
  };
  return {ctx,root,second,registry,live,owners,roots,manager,observer,source,poolFor,add,setLimit:value=>{limit=value;},advance:value=>{time+=value;}};
}
const config={normal_slots:7,reserve_slots:1};
const capture=async(f,caller=f.root)=>{const result=await f.observer.capture(f.ctx,caller);assert.equal(result.capacity_known,true,JSON.stringify(result));return result.snapshot;};

test('exact root capture proves absent-pool zero without creating anything',async()=>{
  const f=fixture(),before=[f.manager.resident.size,f.manager.materializations.size,f.manager.rootPools.get(f.root)];
  const snapshot=await capture(f);
  assert.equal(snapshot.pool_capacity.absent_pool_zero_proven,true);assert.equal(snapshot.pool_capacity.reserved_slots,0);
  assert.deepEqual([f.manager.resident.size,f.manager.materializations.size,f.manager.rootPools.get(f.root)],before);
  assert.equal(snapshot.allocation_scope,'root-activation-pool');assert.equal(snapshot.host_capacity,undefined);
  assert.equal((await f.observer.verify(f.ctx,f.root,JSON.parse(JSON.stringify(snapshot)))).root_agent_id,f.root.id);
});

test('all resident manager roles share the exact root pool through two-level ownership',async()=>{
  const f=fixture(),pool=f.poolFor(f.root);
  for(const [index,role] of ['mcm-model-lead','mcm-paper-lead','mcm-code-lead'].entries()) {
    const manager=f.add(f.root,pool,role),leaf=f.add(manager.agent,pool,'leaf-'+index);
    const snapshot=await capture(f,manager.agent);
    assert.equal(snapshot.root_agent_id,f.root.id);assert.equal(snapshot.caller_agent_id,manager.agent.id);
    assert.equal(snapshot.pool_capacity.reserved_slots,(index+1)*2);
    assert.ok((await f.observer.verify(f.ctx,manager.agent,snapshot)).allocation_domain_id);
    // A durable-like same-id object or a different caller cannot reuse it.
    await assert.rejects(f.observer.verify(f.ctx,{id:manager.agent.id},snapshot),/exact caller/);
    assert.notEqual(leaf.agent,manager.agent);
  }
  const rootSnapshot=await capture(f),leadSnapshot=await capture(f,f.live.get('mcm-model-lead'));
  assert.equal(rootSnapshot.allocation_domain_id,leadSnapshot.allocation_domain_id);
});

test('two roots have distinct domains; unrelated materialization does not consume this pool',async()=>{
  const f=fixture(),pool=f.poolFor(f.root),other=f.poolFor(f.second);
  const local=f.add(f.root,pool,'own');
  other.slots.add(Symbol('not-published'));f.manager.materializations.add({lineage:[f.second]});
  const first=await capture(f);assert.equal(first.pool_capacity.reserved_slots,1);
  const second=await f.observer.capture(f.ctx,f.second);assert.equal(second.capacity_known,false);assert.equal(second.snapshot.pool_capacity.reserved_slots,1);
  assert.notEqual(first.allocation_domain_id,second.snapshot.allocation_domain_id);
  assert.equal((await f.observer.verify(f.ctx,f.root,first)).root_agent_id,f.root.id);local.release();
});

test('same-id Agent, registry, service, manager and pool replacements invalidate capture',async()=>{
  for(const replacement of ['agent','registry','service','manager','pool']) {
    const f=fixture(),pool=f.poolFor(f.root),snapshot=await capture(f);
    if(replacement==='agent')f.live.set(f.root.id,{id:f.root.id});
    if(replacement==='registry') {f.ctx.agents={...f.registry};f.manager.ctx.agents=f.ctx.agents;}
    if(replacement==='service')f.ctx.subagents={...f.ctx.subagents};
    if(replacement==='manager')f.ctx.subagents.manager={...f.manager};
    if(replacement==='pool')f.manager.rootPools.set(f.root,{slots:new Set()});
    await assert.rejects(f.observer.verify(f.ctx,f.root,snapshot),/exact live|changed/);
    assert.equal(pool.slots.size,0);
  }
});

test('pending reservation before publish has a real count but never fake child IDs or admission',async()=>{
  const f=fixture(),pool=f.poolFor(f.root),slot=Symbol('pending');pool.slots.add(slot);
  const pending={lineage:[f.root]};f.manager.materializations.add(pending);
  let result=await f.observer.capture(f.ctx,f.root);
  assert.equal(result.capacity_known,false);assert.equal(result.snapshot.pool_capacity.reserved_slots,1);assert.deepEqual(result.snapshot.records,[]);
  assert.ok(result.snapshot.coverage_gaps.includes('reservations-not-reconciled-with-residents'));
  await assert.rejects(f.observer.verify(f.ctx,f.root,result.snapshot),/not captured/);
  // Publish first, then remove the tracked materialization. Its reservation
  // remains visible through both phases, so neither phase admits too early.
  const child=f.add(f.root,pool,'published');pool.slots.delete(child.slot);
  result=await f.observer.capture(f.ctx,f.root);assert.equal(result.capacity_known,false);assert.equal(result.snapshot.records[0].agent_id,'published');
  f.manager.materializations.delete(pending);result=await f.observer.capture(f.ctx,f.root);assert.equal(result.capacity_known,true);assert.equal(result.snapshot.pool_capacity.reserved_slots,1);
});

test('idle and closing residents retain slots; release invalidates old evidence and returns capacity',async()=>{
  const f=fixture({limit:3}),pool=f.poolFor(f.root),idle=f.add(f.root,pool,'idle'),closing=f.add(f.root,pool,'closing',{closing:true,kind:'external'});
  const snapshot=await capture(f),capacity=capacityOf(config,snapshot,100000);
  assert.equal(capacity.allocated,2);assert.equal(capacity.effective_normal_slots,2);assert.equal(capacity.admit_one_task,false);
  assert.equal(snapshot.records.find(row=>row.agent_id==='closing').closing,true);
  closing.release();await assert.rejects(f.observer.verify(f.ctx,f.root,snapshot),/changed/);
  const fresh=await capture(f);assert.equal(capacityOf(config,fresh,100000).admit_one_task,true);idle.release();
});

test('same-count reservation replacement and materialization rollback invalidate old evidence',async()=>{
  const f=fixture(),pool=f.poolFor(f.root),child=f.add(f.root,pool,'child'),snapshot=await capture(f);
  pool.slots.delete(child.slot);pool.slots.add(Symbol('new-reservation'));
  await assert.rejects(f.observer.verify(f.ctx,f.root,snapshot),/changed/);
  const before=f.manager.resident.size;f.manager.materializations.add({lineage:[f.root]});pool.slots.add(Symbol('rollback'));
  assert.equal((await f.observer.capture(f.ctx,f.root)).capacity_known,false);
  assert.equal(f.manager.resident.size,before);
});

test('unknown absent-pool state, draining, closing root and source drift deny',async()=>{
  for(const mutate of [
    f=>f.manager.materializations.add({lineage:[f.second]}),f=>{f.manager.draining=true;},
    f=>f.manager.closingScopes.set(f.root,new Set([f.root])),f=>{f.source.pin={...SOURCE_PIN,version:'other'};},
    f=>{f.ctx.subagents.manager=undefined;},f=>{f.manager.materializations.add({});}
  ]) {const f=fixture();mutate(f);assert.equal((await f.observer.capture(f.ctx,f.root)).capacity_known,false);}
  const f=fixture(),snapshot=await capture(f);f.source.pin={...SOURCE_PIN,version:'other'};
  await assert.rejects(f.observer.verify(f.ctx,f.root,snapshot),/unsupported source/);
  await assert.rejects(verifyRuntimeSource(f.ctx),/executing class/); // No package import is reached.
});

test('limit changes, stale captures, ownership gaps and ambiguous pool roots deny',async()=>{
  const f=fixture(),pool=f.poolFor(f.root),manager=f.add(f.root,pool,'manager'),snapshot=await capture(f,manager.agent);
  f.setLimit(4);await assert.rejects(f.observer.verify(f.ctx,manager.agent,snapshot),/changed/);
  f.setLimit(8);let fresh=await capture(f,manager.agent);f.advance(60001);await assert.rejects(f.observer.verify(f.ctx,manager.agent,fresh),/not captured/);
  f.owners.delete(manager.agent.id);assert.equal((await f.observer.capture(f.ctx,manager.agent)).capacity_known,false);
  f.owners.set(manager.agent.id,f.root);f.manager.rootPools.set(f.second,pool);assert.equal((await f.observer.capture(f.ctx,manager.agent)).capacity_known,false);
});

test('forged JSON or legacy host verified=true never mints process-local capture authority',async()=>{
  const f=fixture(),snapshot=await capture(f),other=createRootPoolObserver({verifySource:async()=>f.source,now:()=>100000});
  await assert.rejects(other.verify(f.ctx,f.root,snapshot),/not captured/);
  await assert.rejects(f.observer.verify(f.ctx,f.root,{...snapshot,capture_id:'forged',pool_capacity:{...snapshot.pool_capacity,verified:true}}),/not captured/);
  await assert.rejects(f.observer.verify(f.ctx,f.root,{allocation_scope:'host',host_capacity:{verified:true,max_active_descendants:8},records:[]}),/root-activation-pool/);
  const serialized=JSON.stringify(snapshot);snapshot.records.push({agent_id:'fake',kind:'local',closing:false});
  await assert.rejects(f.observer.verify(f.ctx,f.root,snapshot),/not captured/);
  assert.ok(await f.observer.verify(f.ctx,f.root,JSON.parse(serialized)));
});

test('pool coverage schema counts every resident and rejects malformed or hidden reservations',async()=>{
  const f=fixture(),pool=f.poolFor(f.root);f.add(f.root,pool,'child');const snapshot=await capture(f);
  for(const change of [s=>{s.records[0].kind='completed';},s=>{s.records[0].closing='false';},s=>{s.records=[];},s=>{s.coverage_gaps=['unknown'];},s=>{s.pool_capacity.pending_materializations=1;},s=>{s.records.push({...s.records[0]});s.pool_capacity.reserved_slots=2;}]) {
    const candidate=structuredClone(snapshot);change(candidate);assert.throws(()=>capacityOf(config,candidate,100000),/root pool/);
  }
});

test('one-use permits reserve by exact shared pool domain without leaking across roots',()=>{
  let time=100000;const ledger=createPermitLedger({now:()=>time}),args={prompt:'a'},validation=domain=>({args_sha256:hash(args),task_id:'T',capacity:{allocated:0,effective_normal_slots:1,captured_ms:time,snapshot_sha256:'one',allocation_domain_id:domain}});
  const a=ledger.issue('captain',validation('A'));assert.equal(ledger.consume('captain',args,a),true);
  assert.throws(()=>ledger.issue('resident-manager',validation('A')),/reservations/);
  const b=ledger.issue('other-root',validation('B'));assert.ok(b);
  time++;const otherEvidence=validation('B');otherEvidence.capacity.snapshot_sha256='other-new';
  ledger.issue('other-root',otherEvidence);
  assert.throws(()=>ledger.issue('resident-manager',validation('A')),/reservations/);
});

test('source origin uses ordinary module resolution when available without reading a desktop entry',async()=>{
  const result=await resolveRuntimePackageUrls({resolveFromPlugin:name=>pathToFileURL(join(tmpdir(),name.split('/').at(-1),'lib/index.js')).href,
    read:()=>assert.fail('ordinary resolution must not read a fallback entry'),resolveFromEntry:()=>assert.fail('must not fall back')});
  assert.equal(result.origin,'plugin-resolution');assert.equal(result.urls.length,3);
});

test('desktop fallback resolves from the actual pinned Node entry without importing or launching SDK',async()=>{
  const runtimeDir=join(tmpdir(),'synthetic-desktop-runtime'),entry=join(runtimeDir,'node_modules','@deepseek-ai','dsh-desktop-host','lib','index.js');
  const entryBytes=Buffer.from('Synthetic offline entry, never executable.'),packageBytes=Buffer.from(JSON.stringify({name:'@deepseek-ai/dsh-desktop-host',version:SOURCE_PIN.version}));
  const pin={...SOURCE_PIN,desktop_host_entry_sha256:hash(entryBytes),desktop_host_package_sha256:hash(packageBytes)};
  let reads=0,resolves=0;
  const request={argv:['node',entry,runtimeDir],pin,resolveFromPlugin:()=>{throw new Error('MODULE_NOT_FOUND');},
    read:async path=>{reads++;if(path===entry)return entryBytes;if(path===join(runtimeDir,'node_modules','@deepseek-ai','dsh-desktop-host','package.json'))return packageBytes;assert.fail('unbounded source read');},
    resolveFromEntry:(actual,name)=>{assert.equal(actual,entry);resolves++;return join(runtimeDir,'node_modules',...name.split('/'),'lib','index.js');}};
  const result=await resolveRuntimePackageUrls(request);assert.equal(result.origin,'pinned-desktop-host-entry');assert.equal(reads,2);assert.equal(resolves,3);
  for(const alter of [
    r=>{r.argv=['node','relative-entry',runtimeDir];},r=>{r.argv=['node',entry,join(runtimeDir,'wrong')];},
    r=>{r.pin={...pin,desktop_host_entry_sha256:hash('wrong')};},r=>{r.pin={...pin,desktop_host_package_sha256:hash('wrong')};},
    r=>{r.resolveFromEntry=()=>join(tmpdir(),'another-sdk','index.js');}
  ]) {const changed={...request};alter(changed);await assert.rejects(resolveRuntimePackageUrls(changed),/desktop|origin/);}
});

test('fresh Cordis-style service wrappers retain canonical identity without trusting caller JSON',async()=>{
  const f=fixture(),rawAgents=f.ctx.agents,rawService=f.ctx.subagents,original=Symbol.for('cordis.original');
  const trace=target=>new Proxy(target,{get(target,key){if(key===original)return target;const value=Reflect.get(target,key);return typeof value==='function'?new Proxy(value,{}):value;}});
  Object.defineProperty(f.ctx,'agents',{configurable:true,get:()=>trace(rawAgents)});
  Object.defineProperty(f.ctx,'subagents',{configurable:true,get:()=>trace(rawService)});
  Object.defineProperty(f.manager.ctx,'agents',{configurable:true,get:()=>trace(rawAgents)});
  assert.notEqual(f.ctx.agents,f.ctx.agents);assert.notEqual(f.ctx.subagents,f.ctx.subagents);
  const snapshot=await capture(f);assert.ok(await f.observer.verify(f.ctx,f.root,snapshot));
  const pool=f.poolFor(f.root),lead=f.add(f.root,pool,'lead');
  const nested=await capture(f,lead.agent);assert.ok(await f.observer.verify(f.ctx,lead.agent,nested));
  Object.defineProperty(f.ctx,'agents',{get:()=>trace({...rawAgents})});
  await assert.rejects(f.observer.verify(f.ctx,lead.agent,nested),/manager binding|identity|changed/);
  // Production attester still rejects fake classes even with an original key.
  await assert.rejects(verifyRuntimeSource({agents:{[original]:rawAgents},subagents:{[original]:rawService}}),/executing class/);
});

test('resident manager closing scope blocks capture even before any closing members are published',async()=>{
  const f=fixture(),pool=f.poolFor(f.root),lead=f.add(f.root,pool,'paper-lead');
  const snapshot=await capture(f,lead.agent);f.manager.closingScopes.set(lead.agent,new Set());
  assert.equal((await f.observer.capture(f.ctx,lead.agent)).capacity_known,false);
  await assert.rejects(f.observer.verify(f.ctx,lead.agent,snapshot),/scope is closing/);
  f.manager.closingScopes.delete(lead.agent);
  assert.equal((await f.observer.capture(f.ctx,lead.agent)).capacity_known,true);
  f.manager.closingScopes.set(f.root,new Set());
  assert.equal((await f.observer.capture(f.ctx,lead.agent)).capacity_known,false);
});
