import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, sep } from 'node:path';
import { capacityOf, createPermitLedger, hash, isDelegation, validateDispatch } from '../src/runtime-guard-core.mjs';
import { apply } from '../src/runtime-guard-plugin.mjs';

async function fixture(t) {
  const root=await mkdtemp(join(tmpdir(),'mcm-guard-'));
  t.after(async()=>{const target=resolve(root);assert.ok(target.startsWith(resolve(tmpdir())+sep)&&target.includes('mcm-guard-'));await rm(target,{recursive:true,force:true});});
  for(const directory of ['.mcm-project','.mcm','config','tasks','data/raw']) await mkdir(join(root,directory),{recursive:true});
  const config={normal_slots:7,reserve_slots:1,max_nested_depth:2,capacity_snapshot_max_age_seconds:60,pause_state:{paused:false},runtime_snapshot:'audit/runtime.json'};
  const task={task_id:'FIG-01',owner_role:'mcm-figure',owner_agent_id:'pending:FIG-01',status:'queued',inputs:[],depends_on:[],allowed_write_paths:['tasks/FIG-01'],acceptance_criteria:['actual figure and source']};
  const snapshot={captured_at:new Date().toISOString(),allocation_scope:'host',host_capacity:{verified:true,max_active_descendants:8,evidence_ref:'isolated test evidence, not user Host'},records:[]};
  const save=async(path,value)=>{await mkdir(join(root,path,'..'),{recursive:true});await writeFile(join(root,path),JSON.stringify(value));};
  await save('config/runtime.json',config);await save('.mcm/tasks.json',{format_version:1,records:[task]});await save('.mcm/artifacts.json',{format_version:1,records:[]});await save('audit/runtime.json',snapshot);
  const args={description:'Build synthetic figure',prompt:'Explicit task, cwd and write scope in task card',agent_preset:'mcm-figure',cwd:root};
  return {root,config,task,snapshot,args,save,request:{root,role:'mcm-paper-lead',depth:1,args,taskId:'FIG-01'}};
}

test('capacity is fail-closed for missing, unverified, stale or timezone-free evidence',()=>{
  const config={normal_slots:7,reserve_slots:1}, valid={captured_at:new Date().toISOString(),allocation_scope:'host',host_capacity:{verified:true,max_active_descendants:8,evidence_ref:'test'},records:[]};
  assert.throws(()=>capacityOf(config,null),/unknown/);
  assert.throws(()=>capacityOf(config,{...valid,allocation_scope:'team'}),/unverified/);
  assert.throws(()=>capacityOf(config,{...valid,captured_at:'2026-01-01T00:00:00'}),/timezone/);
  assert.throws(()=>capacityOf(config,{...valid,captured_at:new Date(Date.now()-61000).toISOString()}),/stale/);
  assert.throws(()=>capacityOf(config,{...valid,captured_at:new Date(Date.now()+10000).toISOString()}),/stale/);
});
test('smaller real capacity retains reserve, and waiting supervisors count',()=>{
  const rows=['running','waiting','starting'].map((state,i)=>({agent_id:String(i),state}));
  const cap=capacityOf({normal_slots:15,reserve_slots:1},{captured_at:new Date().toISOString(),allocation_scope:'host',host_capacity:{verified:true,max_active_descendants:4,evidence_ref:'test'},records:rows});
  assert.equal(cap.effective_normal_slots,3);assert.equal(cap.admit_one_task,false);assert.equal(cap.allocated,3);
});
test('malformed string root flags or nonstring evidence cannot hide occupied slots',()=>{
  const config={normal_slots:7,reserve_slots:1}, snapshot={captured_at:new Date().toISOString(),allocation_scope:'host',host_capacity:{verified:true,max_active_descendants:8,evidence_ref:'test'},records:[{agent_id:'busy',state:'running',is_root:'false'}]};
  assert.throws(()=>capacityOf(config,snapshot),/invalid Host allocation record/);
  snapshot.records[0].is_root=false;assert.equal(capacityOf(config,snapshot).allocated,1);
  snapshot.host_capacity.evidence_ref={};assert.throws(()=>capacityOf(config,snapshot),/unverified/);
});
test('registered compatible task and exact original cwd pass without changing registries',async t=>{
  const f=await fixture(t), before=await readFile(join(f.root,'.mcm/tasks.json'));
  const checked=await validateDispatch(f.request);assert.equal(checked.task_id,'FIG-01');assert.equal(checked.args_sha256,hash(f.args));assert.deepEqual(await readFile(join(f.root,'.mcm/tasks.json')),before);
  f.task.owner_role='figure_editor';await f.save('.mcm/tasks.json',{format_version:1,records:[f.task]});await validateDispatch(f.request);
});
test('actual parent role and real depth gate native preset independently of names',async t=>{
  const f=await fixture(t);
  await assert.rejects(validateDispatch({...f.request,role:'mcm-writer'}),/actual parent role/);
  await assert.rejects(validateDispatch({...f.request,depth:2}),/depth exceeds 2/);
  await assert.rejects(validateDispatch({...f.request,args:{...f.args,cwd:tmpdir()}}),/original absolute project root/);
});
test('unset snapshot and explicit admit=false never become a capacity probe',async t=>{
  const f=await fixture(t);f.config.runtime_snapshot=null;await f.save('config/runtime.json',f.config);
  await assert.rejects(validateDispatch(f.request),/runtime_snapshot is unset/);
  f.config.runtime_snapshot='audit/runtime.json';await f.save('config/runtime.json',f.config);f.snapshot.admit_one_task=false;await f.save('audit/runtime.json',f.snapshot);
  await assert.rejects(validateDispatch(f.request),/explicitly denies/);
});
test('unknown tasks, wrong owners, absent acceptance and unsafe write scope fail closed',async t=>{
  const f=await fixture(t);await assert.rejects(validateDispatch({...f.request,taskId:'missing'}),/unknown/);
  f.task.owner_role='mcm-writer';await f.save('.mcm/tasks.json',{format_version:1,records:[f.task]});await assert.rejects(validateDispatch(f.request),/owner_role/);
  f.task.owner_role='mcm-figure';f.task.acceptance_criteria=[];await f.save('.mcm/tasks.json',{format_version:1,records:[f.task]});await assert.rejects(validateDispatch(f.request),/acceptance criteria/);
  f.task.acceptance_criteria=['pass'];f.task.allowed_write_paths=['data/raw/x'];await f.save('.mcm/tasks.json',{format_version:1,records:[f.task]});await assert.rejects(validateDispatch(f.request),/read only/);
  f.task.allowed_write_paths=['../outside'];await f.save('.mcm/tasks.json',{format_version:1,records:[f.task]});await assert.rejects(validateDispatch(f.request),/without/);
});
test('pause, unapproved dependencies and reclaimed ownership block a task',async t=>{
  const f=await fixture(t);f.config.pause_state.paused=true;await f.save('config/runtime.json',f.config);await assert.rejects(validateDispatch(f.request),/pause/);
  f.config.pause_state.paused=false;await f.save('config/runtime.json',f.config);f.task.depends_on=['missing'];await f.save('.mcm/tasks.json',{format_version:1,records:[f.task]});await assert.rejects(validateDispatch(f.request),/dependency/);
  f.task.depends_on=[];f.task.handover={from_agent_id:'old',permission_granted:true,permission_expires_at:new Date(Date.now()+60000).toISOString(),reclaimed_at:new Date().toISOString()};await f.save('.mcm/tasks.json',{format_version:1,records:[f.task]});await assert.rejects(validateDispatch(f.request),/reclaimed/);
});
test('upstream input bytes and path/version/hash references are independently bound',async t=>{
  const f=await fixture(t);await writeFile(join(f.root,'tasks/input.txt'),'original');const artifact={artifact_id:'DATA',path:'tasks/input.txt',version:'1',sha256:hash('original'),status:'verified'};
  f.task.inputs=[{artifact_id:'DATA',path:artifact.path,version:'1',sha256:artifact.sha256}];await f.save('.mcm/tasks.json',{format_version:1,records:[f.task]});await f.save('.mcm/artifacts.json',{format_version:1,records:[artifact]});await validateDispatch(f.request);
  await writeFile(join(f.root,'tasks/input.txt'),'changed');await assert.rejects(validateDispatch(f.request),/bytes changed/);
});
test('one exact permission can be consumed once under concurrent attempts, expires, and reserves capacity',()=>{
  let time=100000;const ledger=createPermitLedger({now:()=>time});const args={prompt:'a'},validation={args_sha256:hash(args),capacity:{allocated:0,effective_normal_slots:1,captured_ms:time,snapshot_sha256:'first'},task_id:'T'};
  const permit=ledger.issue('parent',validation);assert.equal(ledger.lookup('other',args),undefined);assert.equal(ledger.lookup('parent',{prompt:'b'}),undefined);
  assert.equal([ledger.consume('parent',args,permit),ledger.consume('parent',args,permit)].filter(Boolean).length,1);
  assert.throws(()=>ledger.issue('parent',{...validation,args_sha256:hash({prompt:'b'})}),/reservations/);
  time+=10;const second=ledger.issue('parent',{...validation,capacity:{...validation.capacity,captured_ms:time,snapshot_sha256:'second'}});time+=60001;assert.equal(ledger.lookup('parent',args),undefined);assert.equal(ledger.consume('parent',args,second),false);
});
test('same or future-skew evidence cannot repeatedly erase already-started reservations',()=>{
  let time=100000;const ledger=createPermitLedger({now:()=>time}),args={prompt:'future'},capacity={allocated:0,effective_normal_slots:1,captured_ms:104000,snapshot_sha256:'future'};
  const permit=ledger.issue('parent',{args_sha256:hash(args),task_id:'F',capacity});assert.equal(ledger.consume('parent',args,permit),true);
  assert.throws(()=>ledger.issue('parent',{args_sha256:hash(args),task_id:'F',capacity}),/reservations/);
  time=106000;assert.throws(()=>ledger.issue('parent',{args_sha256:hash(args),task_id:'F',capacity}),/reservations/);
  assert.throws(()=>ledger.issue('parent',{args_sha256:hash(args),task_id:'F',capacity:{...capacity,captured_ms:107000,snapshot_sha256:'new-but-future'}}),/reservations/);
  assert.ok(ledger.issue('parent',{args_sha256:hash(args),task_id:'F',capacity:{...capacity,captured_ms:105000,snapshot_sha256:'genuinely-later'}}));
});
test('alternate delegation names are recognized while ordinary communication remains available',()=>{
  for(const name of ['subagent','subagent_fork','subagent_codex','subagent_claude_code','spawn_teammate','task_board_run','team_task_run']) assert.equal(isDelegation(name),true,name);
  for(const name of ['send_message','read','pwsh','mcm_runtime_readback']) assert.equal(isDelegation(name),false,name);
});
test('monotonic guard denies bypass and atomically consumes only a revalidated exact permit',async t=>{
  const f=await fixture(t);const tools=new Map(), agent={id:'captain-test',session:{header:{cwd:f.root,delegationDepth:1}},ctx:{}}, callbacks={};let guard;
  const ctx={tools:{register:d=>tools.set(d.name,d),guard:g=>{guard=g;}},on:(name,fn)=>{callbacks[name]=fn;},agentPresets:{composedPreset:()=> 'mcm-paper-lead'},subagents:{config:{maxActiveSubagents:{get:()=>8}}}};
  apply(ctx,{role:'mcm-paper-lead'});const execution=()=>({agent,name:'subagent',arguments:JSON.parse(JSON.stringify(f.args)),signal:new AbortController().signal});
  assert.match(guard(execution()),/missing/);
  await assert.rejects(callbacks['tools/pre-execute'](execution(),async()=>({kind:'allow'})),/one-use/);
  await tools.get('mcm_dispatch_preflight').execute({task_id:'FIG-01',subagent_arguments:f.args},{agent});
  const good=execution();await callbacks['tools/pre-execute'](good,async()=>({kind:'allow'}));assert.equal(guard(good),undefined);assert.match(guard(good),/consumed/);
  assert.match(guard({...execution(),name:'subagent_codex'}),/alternate/);
});
test('body-stage asynchronous delay cannot outlive the permit even when capacity evidence lasts longer',async t=>{
  const f=await fixture(t);f.config.capacity_snapshot_max_age_seconds=300;await f.save('config/runtime.json',f.config);
  const tools=new Map(), callbacks={}, agent={id:'expiry-body',session:{header:{cwd:f.root,delegationDepth:1}},ctx:{}};let guard;
  const ctx={tools:{register:d=>tools.set(d.name,d),guard:g=>{guard=g;}},on:(name,fn)=>{callbacks[name]=fn;},agentPresets:{composedPreset:()=> 'mcm-paper-lead'},subagents:{config:{maxActiveSubagents:{get:()=>8}}}};
  apply(ctx,{role:'mcm-paper-lead'});const execution={agent,name:'subagent',arguments:f.args,signal:new AbortController().signal};
  await tools.get('mcm_dispatch_preflight').execute({task_id:'FIG-01',subagent_arguments:f.args},{agent});
  await callbacks['tools/pre-execute'](execution,async()=>({kind:'allow'}));assert.equal(guard(execution),undefined);
  const realClock=Date.now, later=realClock()+61000;Date.now=()=>later;
  try {await assert.rejects(callbacks['tools/execute'](execution,async()=>{throw new Error('native body must not run');}),/permit expired/);} finally {Date.now=realClock;}
});
