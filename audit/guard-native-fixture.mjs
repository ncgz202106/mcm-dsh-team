import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';

export const name='mcm-guard-native-fixture';
export const inject=['agents','agentPresets','tools','llm','subagents','sessions','sessionQuery','sessionPersistence','sessionProjections'];

export function apply(ctx,config) {
 const run=async()=>{
  await ctx.get('loader')?.await();
  await mkdir(join(config.project,'audit'),{recursive:true});
  const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
  assert.equal(hash(await readFile(config.fixturePath)),config.fixtureSha256,'Guard fixture changed before execution');
  assert.equal(hash(await readFile(config.launcherPath)),config.launcherSha256,'Launcher changed before execution');
  const load=pkg=>import(pathToFileURL(join(config.runtimeRoot,'node_modules','@deepseek-ai',pkg,'lib/index.js')).href);
  const {LlmAdapter,createUserMessage}=await load('dsh-llm');
  const {scopeOf}=await load('dsh-scope');
  const held=new Map();const roots=new Set();const unheld=new Set();const actions=new Map();const ownedChildren=new Set();let hold=true;
  class Scripted extends LlmAdapter {
   async resolveModel(provider,model){return{provider,id:model,name:model,contextWindow:128000,inputModalities:['text']};}
   async *stream(request){
    if(hold&&!roots.has(request.sessionId)&&!unheld.has(request.sessionId))await new Promise(done=>held.set(request.sessionId,done));
    const action=actions.get(request.sessionId);
    if(action&&!action.used){
     action.used=true;
     yield{type:'block-start',index:0,blockType:'tool-call'};
     yield{type:'block-end',index:0,block:{type:'tool-call',id:action.callId,name:'run_code',arguments:JSON.stringify({code:action.code,description:`Synthetic native guard test: ${action.label}`})}};
    }else{
     yield{type:'block-start',index:0,blockType:'text'};
     yield{type:'block-end',index:0,block:{type:'text',text:'Synthetic guard-fixture completion.'}};
    }
    yield{type:'finish',reason:{kind:'stop'}};
   }
  }
  ctx.llm.registerAdapter(['mcm-smoke'],new Scripted());
  for(const[path,expected]of Object.entries(config.fingerprints))assert.equal(hash(await readFile(join(config.bundlePath,path))),expected,`Bundle drift before test ${path}`);
  let dummyCalls=0;
  const alternatives=['subagent_codex','subagent_claude_code','spawn_teammate','subagent_fork'];
  for(const name of alternatives)ctx.tools.register({name,description:'Synthetic alternative-delegation spy; must not execute.',parameters:{type:'object',additionalProperties:true,properties:{}},output:{schema:{type:'object',properties:{called:{type:'boolean'}},required:['called']},render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]},execute:async()=>{dummyCalls++;return{called:true};}});
  const checks=[];const evidence=[];let callCounter=0;
  const handle=await ctx.agents.create({sessionId:'guard-native-captain',meta:{cwd:config.project,agentPreset:'mcm-captain'},agentOptions:{provider:'mcm-smoke',model:'scripted'},setup:async(agentCtx)=>{await ctx.agentPresets.mount(agentCtx,'mcm-captain');}});
  const captain=handle.agent;roots.add(captain.id);
  const tick=()=>new Promise(done=>setTimeout(done,10));
  const waitFor=async(predicate,title)=>{const end=Date.now()+10000;while(!predicate()){if(Date.now()>end)throw new Error(`Timed out: ${title}`);await tick();}};
  const findMarker=(value,label)=>{
   if(!value||typeof value!=='object')return;
   if(value.__mcm_guard_fixture===label)return value;
   if(Array.isArray(value)){for(const child of value){const found=findMarker(child,label);if(found)return found;}}
   else for(const[key,child]of Object.entries(value)){
    if(key==='text'&&typeof child==='string'){
     const start=child.indexOf('{'),end=child.lastIndexOf('}');
     if(start>=0&&end>start)try{const found=findMarker(JSON.parse(child.slice(start,end+1)),label);if(found)return found;}catch{}
    }
    const found=findMarker(child,label);if(found)return found;
   }
  };
  const ptc=async(agent,code,label)=>{
   const wrapped=`try { const value = await (async()=>{${code}})(); return {__mcm_guard_fixture:${JSON.stringify(label)},ok:true,value}; } catch(error) { return {__mcm_guard_fixture:${JSON.stringify(label)},ok:false,error:String(error?.message??error)}; }`;
   actions.set(agent.id,{used:false,code:wrapped,label,callId:`guard-${++callCounter}-${label}`});
   agent.followup(createUserMessage({content:[{type:'text',text:`SYNTHETIC_GUARD_ACTION ${label}`}],source:{kind:'user'}}));
   if(held.has(agent.id)){unheld.add(agent.id);held.get(agent.id)();held.delete(agent.id);}
   await agent.whenIdle();
   const liveSession=ctx.sessions.get(agent.id);if(liveSession)await ctx.sessions.flush(liveSession);
   const reader=await ctx.sessionPersistence.open(agent.id,'read');let result;
   try{result=(await reader.read(0)).events.filter(event=>event.type==='tool/result');}finally{await reader.close();}
   const decoded=findMarker(result,label);
   if(!decoded){await writeFile(join(config.work,'guard-last-result.json'),JSON.stringify(result,null,2));throw new Error(`No PTC return marker for ${label}; inspect isolated guard-last-result.json`);}
   evidence.push({label,agent_id:agent.id,ok:decoded.ok,...decoded.ok?{}:{error:decoded.error}});
   return decoded;
  };
  const denied=(result,pattern=/MCM|admission|permit|capacity|snapshot|paused|delegat|blocked|denied/i)=>{assert.equal(result.ok,false,JSON.stringify(result));assert.match(result.error,pattern);};
  const configPath=join(config.project,'config/runtime.json');
  const originalConfig=JSON.parse(await readFile(configPath,'utf8'));
  const snapshotPath='audit/guard-fixture-runtime.json';
  const tasks=[];
  const configure=async({snapshot=true,age=0,allocated,paused=false,explicitAdmitFalse=false}={})=>{
   await writeFile(configPath,JSON.stringify({...originalConfig,runtime_snapshot:snapshot?snapshotPath:null,pause_state:{paused,reason:paused?'Synthetic negative test':null,user_message_ref:null,recorded_at:new Date().toISOString()}},null,2));
   const records=allocated===undefined?[...ownedChildren].filter(id=>ctx.agents.get(id)).map(id=>({agent_id:id,state:ctx.agents.get(id).status==='idle'?'waiting':'running',is_root:false,role:ctx.agentPresets.composedPreset(ctx.agents.get(id).ctx)})):Array.from({length:allocated},(_,i)=>({agent_id:`synthetic-negative-occupied-${i}`,state:'running',is_root:false,role:'mcm-evidence'}));
   if(snapshot)await writeFile(join(config.project,snapshotPath),JSON.stringify({captured_at:new Date(Date.now()-age).toISOString(),allocation_scope:'host',host_capacity:{verified:true,max_active_descendants:8,evidence_ref:'Synthetic isolated harness exclusively owns all activation roots/reservations; currently published children are tracked by exact ids and live registry entries, including idle supervisors. Native subagents.config.maxActiveSubagents getter is checked as 8. Injected occupancy rows are used only by explicit negative scenarios.'},records,...(explicitAdmitFalse?{admit_one_task:false}:{}),synthetic:true},null,2));
  };
  const task=async(id,preset)=>{
   tasks.push({task_id:id,owner_role:preset,owner_agent_id:`pending:${id}`,status:'queued',allowed_write_paths:[`tasks/${id}`],acceptance_criteria:['Synthetic child returns under the declared native preset.'],inputs:[],depends_on:[],read_only:false,synthetic:true});
   await writeFile(join(config.project,'.mcm/tasks.json'),JSON.stringify({format_version:1,records:tasks},null,2));
   return{description:id,prompt:`Synthetic isolated admission task ${id}; do no file writes and return.`,agent_preset:preset,cwd:config.project};
  };
  const preflight=(args,id)=>`return await tools.mcm_dispatch_preflight(${JSON.stringify({task_id:id,subagent_arguments:args})});`;
  const spawn=args=>`return await tools.subagent(${JSON.stringify(args)});`;
  assert.equal(ctx.subagents.config.maxActiveSubagents.get(),8,'Fixture expects verified default Host capacity 8, does not override it');
  await configure({snapshot:false});
  const unknownArgs=await task('GUARD-UNKNOWN','mcm-evidence');
  denied(await ptc(captain,preflight(unknownArgs,'GUARD-UNKNOWN'),'unknown-preflight'));
  denied(await ptc(captain,spawn(unknownArgs),'unpermitted-native-spawn'));
  assert.equal((await ctx.subagents.listChildren(captain.id)).length,0);
  checks.push({name:'unknown_capacity_and_direct_native_spawn_blocked_through_ptc',passed:true,child_count:0});
  await configure({age:120000});
  denied(await ptc(captain,preflight(unknownArgs,'GUARD-UNKNOWN'),'expired-snapshot'));
  await configure({allocated:7});
  denied(await ptc(captain,preflight(unknownArgs,'GUARD-UNKNOWN'),'normal_capacity_exhausted'));
  await configure({explicitAdmitFalse:true});
  denied(await ptc(captain,preflight(unknownArgs,'GUARD-UNKNOWN'),'snapshot_explicit_admit_false'));
  await configure({paused:true});
  denied(await ptc(captain,preflight(unknownArgs,'GUARD-UNKNOWN'),'paused-preflight'));
  checks.push({name:'expired_exhausted_and_paused_admission_blocked_through_ptc',passed:true});
  await configure();
  const pauseArgs=await task('GUARD-PAUSE-AFTER','mcm-evidence');
  const pausePermit=await ptc(captain,preflight(pauseArgs,'GUARD-PAUSE-AFTER'),'issue-before-pause');assert.equal(pausePermit.ok,true);
  await configure({paused:true});
  denied(await ptc(captain,spawn(pauseArgs),'pause-after-preflight'));
  assert.equal((await ctx.subagents.listChildren(captain.id)).length,0);
  checks.push({name:'pause_after_permit_before_native_dispatch_blocks',passed:true});
  await configure({age:55000});
  const expiringArgs=await task('GUARD-PERMIT-EXPIRY','mcm-evidence');
  const expiring=await ptc(captain,preflight(expiringArgs,'GUARD-PERMIT-EXPIRY'),'expiring-permit-issued');assert.equal(expiring.ok,true);
  const untilExpiry=Date.parse(expiring.value.expires_at)-Date.now();assert.ok(untilExpiry>=0&&untilExpiry<=5500,'Permit must not outlive snapshot freshness');
  await new Promise(done=>setTimeout(done,untilExpiry+50));
  denied(await ptc(captain,spawn(expiringArgs),'naturally-expired-permit'));
  assert.equal((await ctx.subagents.listChildren(captain.id)).length,0);
  checks.push({name:'permit_natural_expiry_blocks_without_artificial_clock_override',passed:true,expires_at:expiring.value.expires_at,waited_ms:untilExpiry+50});
  await configure();
  const leadArgs=await task('GUARD-PAPER','mcm-paper-lead');
  const leadPermit=await ptc(captain,preflight(leadArgs,'GUARD-PAPER'),'paper-preflight');assert.equal(leadPermit.ok,true);assert.equal(leadPermit.value.admitted,true);
  const mutated={...leadArgs,prompt:leadArgs.prompt+' MUTATED'};
  denied(await ptc(captain,spawn(mutated),'bound-prompt-mutation'));
  const leadResult=await ptc(captain,spawn(leadArgs),'paper-native-spawn');assert.equal(leadResult.ok,true);
  const leadId=leadResult.value.subagentId;
  ownedChildren.add(leadId);
  await waitFor(()=>ctx.agents.get(leadId)&&held.has(leadId),'paper lead mounted and held');
  const lead=ctx.agents.get(leadId);
  assert.equal(ctx.agentPresets.composedPreset(lead.ctx),'mcm-paper-lead');assert.equal(lead.session.header.delegationDepth,1);
  checks.push({name:'fresh_evidence_permit_exact_arguments_native_dispatch',passed:true,lead_id:leadId,actual_preset:'mcm-paper-lead',actual_depth:1});
  await configure();
  const leafArgs=await task('GUARD-FIGURE','mcm-figure');
  const concurrent=await ptc(lead,`${preflight(leafArgs,'GUARD-FIGURE').replace(/^return /,'const permit = ')} return await Promise.all([0,1].map(async()=>{try{return{ok:true,value:await tools.subagent(${JSON.stringify(leafArgs)})};}catch(error){return{ok:false,error:String(error?.message??error)};}}));`,'one-permit-concurrent-spawn');
  assert.equal(concurrent.ok,true);assert.equal(concurrent.value.filter(x=>x.ok).length,1);assert.equal(concurrent.value.filter(x=>!x.ok).length,1);
  const leafId=concurrent.value.find(x=>x.ok).value.subagentId;
  ownedChildren.add(leafId);
  await waitFor(()=>ctx.agents.get(leafId)&&held.has(leafId),'figure leaf mounted and held');
  const leaf=ctx.agents.get(leafId);
  assert.equal(ctx.agentPresets.composedPreset(leaf.ctx),'mcm-figure');assert.equal(leaf.session.header.parentSession,leadId);assert.equal(leaf.session.header.delegationDepth,2);
  checks.push({name:'single_permit_concurrent_consumption_at_most_once',passed:true,accepted:1,rejected:1,leaf_id:leafId});
  const selfRead=await ptc(lead,'return await tools.mcm_runtime_readback({});','role-self-readback');assert.equal(selfRead.ok,true);
  const childRead=await ptc(lead,`return await tools.mcm_runtime_readback({child_session_id:${JSON.stringify(leafId)}});`,'role-live-child-readback');assert.equal(childRead.ok,true);
  await writeFile(join(config.work,'guard-readback-live.json'),JSON.stringify({self:selfRead.value,child:childRead.value},null,2));
  assert.equal(selfRead.value.session_id,leadId);assert.equal(selfRead.value.effective_preset,'mcm-paper-lead');assert.equal(selfRead.value.parent_session_id,captain.id);assert.equal(selfRead.value.delegation_depth,1);assert.equal(selfRead.value.live_agent_present,true);
  assert.equal(childRead.value.session_id,leafId);assert.equal(childRead.value.effective_preset,'mcm-figure');assert.equal(childRead.value.parent_session_id,leadId);assert.equal(childRead.value.delegation_depth,2);assert.equal(childRead.value.live_agent_present,true);assert.equal(childRead.value.loaded_or_resumed_session,false);assert.equal(childRead.value.capacity_known,false);
  const unauthorized=await ptc(captain,`return await tools.mcm_runtime_readback({child_session_id:${JSON.stringify(leafId)}});`,'non-direct-child-readback');denied(unauthorized,/direct|child|authoriz|MCM/i);
  checks.push({name:'native_actual_role_parent_depth_and_direct_child_authorization',passed:true,self:selfRead.value,live_child:childRead.value});
  for(const alternative of alternatives)denied(await ptc(captain,`return await tools.${alternative}({});`,`captain-${alternative}`));
  const leafAlternatives=await ptc(leaf,`return await Promise.all(${JSON.stringify(alternatives)}.map(async name=>{try{return {name,ok:true,value:await tools[name]({})};}catch(error){return{name,ok:false,error:String(error?.message??error)};}}));`,'leaf-global-alternatives');
  assert.equal(leafAlternatives.ok,true);for(const result of leafAlternatives.value)denied(result);
  assert.equal(dummyCalls,0);
  checks.push({name:'global_alternative_delegation_tools_cannot_bypass_native_policy',passed:true,names:alternatives,dummy_tool_bodies_executed:dummyCalls,roles:['mcm-captain','mcm-figure']});
  hold=false;for(const done of held.values())done();held.clear();
  while(true){await captain.whenIdle();const before=captain.session.seq;if(!await ctx.subagents.waitForChildren(captain)&&captain.status==='idle'&&before===captain.session.seq)break;}
  assert.equal(ctx.agents.get(leafId),undefined);
  const historical=await ptc(captain,`return await tools.mcm_runtime_readback({child_session_id:${JSON.stringify(leadId)}});`,'historical-child-readback');assert.equal(historical.ok,true);
  assert.equal(historical.value.session_id,leadId);assert.equal(historical.value.effective_preset,'mcm-paper-lead');assert.equal(historical.value.live_agent_present,false);assert.equal(historical.value.loaded_or_resumed_session,false);
  checks.push({name:'completed_child_readback_uses_history_without_resuming',passed:true,result:historical.value,child_live_after_readback:Boolean(ctx.agents.get(leadId))});
  await ctx.sessions.flush(captain.session);
  const reader=await ctx.sessionPersistence.open(captain.id,'read');let events;try{events=(await reader.read(0)).events;}finally{await reader.close();}
  const nativeNestedCalls=events.filter(e=>e.type==='tool/ptc-dispatch-start'&&['subagent','mcm_dispatch_preflight','mcm_runtime_readback',...alternatives].includes(e.data.name)).map(e=>({seq:e.seq,name:e.data.name,time:e.time}));
  assert.ok(nativeNestedCalls.some(e=>e.name==='subagent'),'PTC nested native subagent event evidence missing');
  assert.ok(nativeNestedCalls.some(e=>e.name==='mcm_dispatch_preflight'),'PTC nested admission event evidence missing');
  checks.push({name:'real_ptc_nested_dispatch_events_recorded',passed:true,event_count:nativeNestedCalls.length,events:nativeNestedCalls});
  for(const[path,expected]of Object.entries(config.fingerprints))assert.equal(hash(await readFile(join(config.bundlePath,path))),expected,`Bundle drift during test ${path}`);
  assert.equal(hash(await readFile(config.fixturePath)),config.fixtureSha256,'Guard fixture changed during execution');
  assert.equal(hash(await readFile(config.launcherPath)),config.launcherSha256,'Launcher changed during execution');
  const runtime=JSON.parse(await readFile(join(config.runtimeRoot,'node_modules/@deepseek-ai/dsh/package.json'),'utf8'));
  await writeFile(config.reportPath,JSON.stringify({schema_version:1,status:'passed',executed_at:new Date().toISOString(),runtime_version:runtime.version,bundle_source:config.bundlePath,bundle_file_sha256:config.fingerprints,fixture_sha256:config.fixtureSha256,launcher_sha256:config.launcherSha256,checks,evidence,isolation:{work:config.work,project:config.project,external_model_calls:false,user_profile_modified:false,live_desktop_modified:false,credentials_read:false},real_components:['real model-stream -> agent loop -> run_code -> tools/pre-execute -> monotonic guard -> native dispatch','real run_code PTC runtime and nested SDK dispatch','actual native spawn/role mount/session persistence','actual read-only role/runtime service'],simulated_components:['Only LLM output uses a deterministic adapter. Capacity input variations are explicitly synthetic negative-test fixtures in an isolated Host. Global alternative delegation tools are spy definitions whose bodies must never run.'],limits:['Not an OS isolation proof; arbitrary shell commands remain outside normal tool dispatch policy.','Not an autonomous external-model or scientific-quality evaluation.','The harness exclusively owns isolated activation roots and verifies the native default limit; it does not claim the user live Host has this capacity.']},null,2)+'\n');
  await handle.dispose();
  ctx.get('appExit')(0);
 };
 run().catch(async error=>{console.error(error.stack??String(error));await writeFile(join(config.work,'guard-fixture-error.txt'),error.stack??String(error));ctx.get('appExit')(1);});
}
