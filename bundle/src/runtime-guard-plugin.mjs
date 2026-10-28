import { isAbsolute } from 'node:path';
import { ROLE_CHILDREN, ROLES, isDelegation, validateDispatch, createPermitLedger } from './runtime-guard-core.mjs';
import { createRootPoolObserver } from './root-pool-observer.mjs';

export const name = 'mcm-runtime-guard';
export const inject = ['tools','agents','agentPresets','subagents','sessions','sessionQuery','sessionPersistence','sessionProjections'];
const definition=(name,description,properties,required,execute)=>({name,description,parameters:{type:'object',additionalProperties:false,properties,required},output:{schema:{type:'object',additionalProperties:true},render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]},execute});
const actualRole=(ctx,agent)=>ctx.agentPresets.composedPreset(agent.ctx)??ctx.sessionProjections.stateOf(agent.session,'agentPreset');
function owningAgent(ctx,exec,role) {
  if(!exec.agent || actualRole(ctx,exec.agent)!==role) throw new Error('MCM_DISPATCH_DENIED: tool owner is not this actual MCM role');
  return exec.agent;
}
function rootOf(agent) {
  const root=agent.session.header.cwd;
  if(typeof root!=='string'||!isAbsolute(root)) throw new Error('MCM_DISPATCH_DENIED: Session has no absolute initial project root');
  return root;
}
function checkCurrentLimit(ctx,validation) {
  const limit=ctx.subagents?.config?.maxActiveSubagents?.get();
  if(!Number.isInteger(limit)||limit<1||validation.capacity.pool_max_active_descendants!==limit) throw new Error('MCM_DISPATCH_DENIED: capacity evidence differs from or cannot be checked against current runtime configured limit');
}
async function toolSnapshot(ctx,sessionId,signal) {
  const live=ctx.sessions.get(sessionId); if(live) await ctx.sessions.flush(live);
  const handle=await ctx.sessionPersistence.open(sessionId,'read',{signal});
  try {
    const {events}=await handle.read(0,undefined,{signal});
    let role=handle.header.agentPreset??null, tools=[],seq=null;
    for(const event of events) {
      if(event.type==='agent-preset/selected') role=event.data?.agentPreset??role;
      if(event.type!=='system/message') continue;
      const text=(event.data?.message?.content??[]).filter(x=>x.type==='text').map(x=>x.text??'').join('\n');
      const match=/(?:interface\s+ToolArgsMap|type\s+ToolArgsMap\s*=)\s*\{(.*?)^\}/ms.exec(text);
      if(match) {tools=[...new Set([...match[1].matchAll(/^  ([A-Za-z_$][\w$]*):/mg)].map(x=>x[1]))].sort();seq=event.seq;}
    }
    return {header:handle.header,role,tools,seq};
  } finally { await handle.close(); }
}

// Constructor-level dependency injection supports offline mock contexts. There
// is no profile setting or model argument that marks evidence as verified.
export function createRuntimeGuard({observer=createRootPoolObserver()}={}) {
 const ledger=createPermitLedger(),prepared=new WeakMap(),admittedExecutions=new WeakSet(),executionAdmissions=new WeakMap();
 return function apply(ctx,config) {
  const role=config?.role;
  if(!ROLES.has(role)) throw new Error('mcm-runtime-guard requires a known role config');
  const manages=Boolean(ROLE_CHILDREN[role]);
  const validate=(agent,options)=>validateDispatch({...options,verifySnapshot:snapshot=>observer.verify(ctx,agent,snapshot)});
  ctx.on('tools/pre-execute',async(exec,next)=>{
    // Enclosing preset observers also receive descendant events. Only the
    // observer matching the actual mounted role owns this execution.
    if(!exec.agent || actualRole(ctx,exec.agent)!==role || !isDelegation(exec.name)) return next();
    if(!manages || exec.name!=='subagent') throw new Error('MCM_DISPATCH_DENIED: alternate delegation is forbidden; leaves cannot delegate');
    const permit=ledger.lookup(exec.agent.id,exec.arguments);
    if(!permit) throw new Error('MCM_DISPATCH_DENIED: native subagent requires a current one-use mcm_dispatch_preflight permit');
    const checked=await validate(exec.agent,{root:rootOf(exec.agent),role,depth:exec.agent.session.header.delegationDepth??0,args:exec.arguments,taskId:permit.task_id,snapshotPath:permit.snapshot_path});
    checkCurrentLimit(ctx,checked);
    if(checked.root!==permit.root || checked.task_sha256!==permit.task_sha256 || checked.evidence_sha256!==permit.evidence_sha256 || checked.args_sha256!==permit.args_sha256 || checked.capacity.snapshot_sha256!==permit.capacity.snapshot_sha256) throw new Error('MCM_DISPATCH_DENIED: task, source evidence or arguments changed after preflight');
    prepared.set(exec,permit);
    return next();
  });
  ctx.tools.guard(exec=>{
    if(!exec.agent || actualRole(ctx,exec.agent)!==role || !isDelegation(exec.name)) return;
    if(!manages || exec.name!=='subagent') return 'MCM_DISPATCH_DENIED: alternate delegation is forbidden; leaves cannot delegate';
    const permit=prepared.get(exec); prepared.delete(exec);
    if(permit) {
      try {observer.assertCurrent(ctx,exec.agent,permit.native_snapshot);} catch(error) {return `MCM_DISPATCH_DENIED: ${error.message}`;}
    }
    if(!permit || !ledger.consume(exec.agent.id,exec.arguments,permit)) return 'MCM_DISPATCH_DENIED: missing, expired or already consumed dispatch permit';
    admittedExecutions.add(exec);
    executionAdmissions.set(exec,permit);
  });
  ctx.on('tools/execute',async(exec,next)=>{
    if(!exec.agent || actualRole(ctx,exec.agent)!==role || !isDelegation(exec.name)) return next();
    if(exec.name!=='subagent'||!admittedExecutions.has(exec)) throw new Error('MCM_DISPATCH_DENIED: delegation body lacks guard admission');
    admittedExecutions.delete(exec);
    // The immutable registry-minted execution already passed exact-argument
    // checks. The body stage nevertheless rechecks pause and capacity against
    // the issued task, closing an async-wrapper delay before native dispatch.
    const accepted=executionAdmissions.get(exec);
    if(!accepted) throw new Error('MCM_DISPATCH_DENIED: missing body-stage admission');
    executionAdmissions.delete(exec);
    if(accepted.expires_ms<=Date.now()) throw new Error('MCM_DISPATCH_DENIED: dispatch permit expired before native body');
    const checked=await validate(exec.agent,{root:rootOf(exec.agent),role,depth:exec.agent.session.header.delegationDepth??0,args:exec.arguments,taskId:accepted.task_id,snapshotPath:accepted.snapshot_path});
    checkCurrentLimit(ctx,checked);
    if(checked.task_sha256!==accepted.task_sha256 || checked.evidence_sha256!==accepted.evidence_sha256 || checked.args_sha256!==accepted.args_sha256 || checked.capacity.snapshot_sha256!==accepted.capacity.snapshot_sha256) throw new Error('MCM_DISPATCH_DENIED: dispatch state changed before native body');
    if(accepted.expires_ms<=Date.now()) throw new Error('MCM_DISPATCH_DENIED: dispatch permit expired during final revalidation');
    return next();
  });

  if(manages) ctx.tools.register(definition('mcm_dispatch_preflight',
    'Validate task, cwd, actual role/depth, pause and fresh root activation pool evidence captured by mcm_root_pool_capture in this process for this exact Agent. Issues a maximum 60-second ONE-USE permit bound to exact native subagent arguments. Unknown/stale/full capacity means queue. Does not create a child or grant human approval.',
    {task_id:{type:'string'},subagent_arguments:{type:'object',additionalProperties:true},snapshot_path:{type:'string'}},['task_id','subagent_arguments'],
    async(args,exec)=>{
      const agent=owningAgent(ctx,exec,role);
      if(!args?.task_id || typeof args.task_id!=='string') throw new Error('MCM_DISPATCH_DENIED: task_id required');
      const checked=await validate(agent,{root:rootOf(agent),role,depth:agent.session.header.delegationDepth??0,args:args.subagent_arguments,taskId:args.task_id,snapshotPath:args.snapshot_path});
      checkCurrentLimit(ctx,checked);
      const permit=ledger.issue(agent.id,checked);
      return {admitted:true,permit_id:permit.permit_id,task_id:permit.task_id,expires_at:new Date(permit.expires_ms).toISOString(),subagent_arguments_sha256:permit.args_sha256,capacity:permit.capacity,human_approval_granted:false,does_not_spawn:true};
    }));

  if(manages) ctx.tools.register(definition('mcm_root_pool_capture',
    'Read only this actual manager Agent root activation pool from the existing injected runtime. Counts reserved slots including pending reconstruction; does not create/resume/interrupt agents or write files. Returns bounded JSON and unknown on unsupported source/identity/coverage. Captain may separately save snapshot under the project and reference it in runtime_snapshot. This is per shared root pool capacity, never a global Desktop/Host maximum or human approval.',
    {},[],async(_args,exec)=>observer.capture(ctx,owningAgent(ctx,exec,role))));

  ctx.tools.register(definition('mcm_runtime_readback',
    'Read actual own or authorized DIRECT child Session role, parent, depth and recorded SDK tool keys without loading or resuming another agent. Reports actual configured child limit, but never invents current Host occupancy or a capacity snapshot. Historical SDK evidence is distinguished from a live mounted preset. No reasoning or credentials are returned.',
    {child_session_id:{type:'string'}},[],
    async(args,exec)=>{
      const owner=owningAgent(ctx,exec,role), requested=args?.child_session_id??owner.id;
      if(requested!==owner.id) {
        const trace=await ctx.sessionQuery?.traceSession(owner.id,exec.signal);
        const allowed=(trace?.descendants??[]).some(node=>node.session?.header?.id===requested && node.session?.header?.parentSession===owner.id);
        if(!allowed) throw new Error('MCM_READBACK_DENIED: only this Session or a cataloged direct child may be read');
      }
      const snapshot=await toolSnapshot(ctx,requested,exec.signal);
      const live=ctx.agents.get(requested);
      const selected=live?actualRole(ctx,live):snapshot.role;
      let limit=null; try {const value=ctx.subagents.config.maxActiveSubagents.get();if(Number.isInteger(value)&&value>0)limit=value;} catch {}
      return {session_id:requested,parent_session_id:snapshot.header.parentSession??null,delegation_depth:snapshot.header.delegationDepth??0,effective_preset:selected,
        cwd:snapshot.header.cwd??null,observed_at:new Date().toISOString(),live_agent_present:Boolean(live),preset_evidence:live?'agentPresets.composedPreset':'Session header plus selected-event projection',
        sdk_tools:{source:'latest persisted system ToolArgsMap snapshot; not a fresh registry enumeration',recorded_seq:snapshot.seq,names:snapshot.tools},
        configured_max_active_descendants:limit,host_allocation_count_known:false,capacity_known:false,
        next_capacity_step:'An actual manager may call mcm_root_pool_capture and separately save its returned snapshot under this project, then set runtime_snapshot. It is bound to that exact calling Agent, service and shared root activation pool. Configured limit or durable children do not prove slots; unknown/stale evidence stays queued.',
        native_child_limit_note:'Runtime configuration limit; residency/remaining allocation is not exposed by this readback. It does not certify a global Host pool, Team member count, or OS isolation.',
        human_gates_modified:false,loaded_or_resumed_session:false};
    }));
 };
}
export const apply=createRuntimeGuard();
