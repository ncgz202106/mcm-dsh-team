import { readFile, realpath, stat } from 'node:fs/promises';
import { resolve, relative, isAbsolute, dirname, join, sep } from 'node:path';
import { createHash, randomUUID } from 'node:crypto';

export const ROLE_CHILDREN = {
  'mcm-captain': ['mcm-model-lead','mcm-evidence','mcm-programmer','mcm-code-lead','mcm-verifier','mcm-paper-lead','mcm-reviewer'],
  'mcm-model-lead': ['mcm-modeler'], 'mcm-paper-lead': ['mcm-writer','mcm-figure','mcm-typesetter'],
  'mcm-code-lead': ['mcm-programmer']
};
export const ROLES = new Set([...Object.keys(ROLE_CHILDREN), ...Object.values(ROLE_CHILDREN).flat()]);
const ALIASES = {captain:'mcm-captain',model_lead:'mcm-model-lead',modeler:'mcm-modeler',researcher:'mcm-evidence',evidence:'mcm-evidence',programmer:'mcm-programmer',verifier:'mcm-verifier',paper_lead:'mcm-paper-lead',paper_writer:'mcm-writer',figure_editor:'mcm-figure',typesetter:'mcm-typesetter',reviewer:'mcm-reviewer',code_lead:'mcm-code-lead'};
export const canonicalRole = role => ALIASES[role] ?? role;
export const stable = value => value === null || typeof value !== 'object' ? JSON.stringify(value) : Array.isArray(value) ? `[${value.map(stable).join(',')}]` : `{${Object.keys(value).sort().map(key=>`${JSON.stringify(key)}:${stable(value[key])}`).join(',')}}`;
export const hash = value => createHash('sha256').update(typeof value === 'string' || Buffer.isBuffer(value) ? value : stable(value)).digest('hex');
export function isDelegation(name) {
  return name === 'subagent' || /^subagent(?:_|$)/i.test(name) || /^(?:spawn_teammate|spawn_agent|agent_spawn|team_member_create|team_member_spawn|team_task_run|team_task_schedule|task_board_run|task_board_schedule|ralph|workflow(?:_.*)?)$/i.test(name);
}
const inside = (root, target) => { const rel=relative(root,target); return rel==='' || (!isAbsolute(rel) && rel!=='..' && !rel.startsWith(`..${sep}`)); };
async function projectPath(root, value, {missing=false, protectRaw=false}={}) {
  if (typeof value!=='string' || !value || isAbsolute(value) || value.split(/[\\/]/).includes('..')) throw new Error('MCM_DISPATCH_DENIED: expected a project-relative path without ..');
  const target=resolve(root,value);
  if (!inside(root,target)) throw new Error('MCM_DISPATCH_DENIED: path escapes project');
  let ancestor=target, tail=[];
  while (true) {
    try { ancestor=await realpath(ancestor); break; }
    catch(error) { if (!missing || error.code!=='ENOENT' || dirname(ancestor)===ancestor) throw error; tail.unshift(ancestor.slice(dirname(ancestor).length+1)); ancestor=dirname(ancestor); }
  }
  const actual=join(ancestor,...tail);
  if (!inside(root,actual)) throw new Error('MCM_DISPATCH_DENIED: symlink escapes project');
  if (protectRaw && inside(join(root,'data','raw'),actual)) throw new Error('MCM_DISPATCH_DENIED: data/raw is read only');
  return actual;
}
const json = async path => { const bytes=await readFile(path); if(bytes.length>8*1024*1024) throw new Error('MCM_DISPATCH_DENIED: project state exceeds bounded read limit'); return JSON.parse(bytes.toString('utf8').replace(/^\uFEFF/,'')); };
function envelope(value,name) { if(value?.format_version!==1 || !Array.isArray(value.records)) throw new Error(`MCM_DISPATCH_DENIED: invalid ${name} registry`); return value.records; }
export function capacityOf(config,snapshot,now=Date.now()) {
  if(!Number.isInteger(config.normal_slots)||config.normal_slots<0||!Number.isInteger(config.reserve_slots)||config.reserve_slots<0) throw new Error('MCM_DISPATCH_DENIED: invalid project capacity');
  if(!snapshot || !Array.isArray(snapshot.records)) throw new Error('MCM_DISPATCH_DENIED: unknown Host capacity; obtain an actual fresh Host allocation snapshot, do not guess');
  const host=snapshot.host_capacity, limit=host?.max_active_descendants;
  if(host?.verified!==true || !Number.isInteger(limit)||limit<=0||typeof host.evidence_ref!=='string'||!host.evidence_ref.trim()||snapshot.allocation_scope!=='host') throw new Error('MCM_DISPATCH_DENIED: unknown or unverified Host allocation capacity');
  const timestamp=snapshot.captured_at;
  if(typeof timestamp!=='string'|| !/(?:Z|[+-]\d\d:\d\d)$/.test(timestamp)) throw new Error('MCM_DISPATCH_DENIED: capacity timestamp requires timezone');
  const captured=Date.parse(timestamp), age=(now-captured)/1000, maximum=config.capacity_snapshot_max_age_seconds??60;
  if(!Number.isFinite(age)||!Number.isFinite(maximum)||maximum<=0||age< -5||age>maximum) throw new Error('MCM_DISPATCH_DENIED: stale or invalid Host capacity snapshot');
  const states=new Set(['running','waiting','starting','paused','completed','cancelled','failed']);
  const allocated=[];
  for(const row of snapshot.records) {
    if(typeof row?.agent_id!=='string'||!row.agent_id.trim()||!states.has(row.state)||(row.is_root!==undefined&&typeof row.is_root!=='boolean')) throw new Error('MCM_DISPATCH_DENIED: invalid Host allocation record');
    if(!row.is_root&&['running','waiting','starting','paused'].includes(row.state)) allocated.push(row.agent_id);
  }
  const total=Math.min(config.normal_slots+config.reserve_slots,limit), normal=Math.min(config.normal_slots,Math.max(0,total-config.reserve_slots));
  if(config.pause_state?.paused===true) throw new Error('MCM_DISPATCH_DENIED: user pause is active');
  if(snapshot.admit_one_task===false) throw new Error('MCM_DISPATCH_DENIED: snapshot explicitly denies admission');
  return {allocated:allocated.length,effective_total:total,effective_normal_slots:normal,admit_one_task:allocated.length<normal,captured_at:timestamp,captured_ms:captured,snapshot_fresh:true,host_capacity_verified:true,host_max_active_descendants:limit,host_evidence_ref:host.evidence_ref,allocated_agents:allocated};
}
export async function validateDispatch({root,role,depth,args,taskId,snapshotPath,now=Date.now()}) {
  if(!ROLE_CHILDREN[role]?.includes(args?.agent_preset)) throw new Error('MCM_DISPATCH_DENIED: actual parent role cannot delegate this preset');
  if(!Number.isInteger(depth)||depth<0||depth+1>2) throw new Error('MCM_DISPATCH_DENIED: actual delegation depth exceeds 2');
  root=await realpath(root);
  if(!(await stat(join(root,'.mcm-project'))).isDirectory()) throw new Error('MCM_DISPATCH_DENIED: no MCM project marker');
  if(!args || typeof args.cwd!=='string'||!isAbsolute(args.cwd)|| await realpath(args.cwd)!==root) throw new Error('MCM_DISPATCH_DENIED: native cwd must equal original absolute project root');
  if(typeof args.prompt!=='string'||!args.prompt.trim()||typeof args.description!=='string'||!args.description.trim()) throw new Error('MCM_DISPATCH_DENIED: native prompt and description required');
  const config=await json(await projectPath(root,'config/runtime.json'));
  if(config.pause_state?.paused===true) throw new Error('MCM_DISPATCH_DENIED: user pause is active');
  const tasks=envelope(await json(await projectPath(root,'.mcm/tasks.json')),'tasks');
  const task=tasks.find(row=>row.task_id===taskId);
  if(!task || task._template_only===true || !['queued','running','rework'].includes(task.status)) throw new Error('MCM_DISPATCH_DENIED: unknown or non-dispatchable task_id');
  if(canonicalRole(task.owner_role)!==args.agent_preset) throw new Error('MCM_DISPATCH_DENIED: task owner_role differs from native preset');
  if(typeof task.owner_agent_id!=='string'||!task.owner_agent_id.trim() || !Array.isArray(task.acceptance_criteria)||!task.acceptance_criteria.length) throw new Error('MCM_DISPATCH_DENIED: task needs owner identity and acceptance criteria');
  if(task.dispatch_parent_role && canonicalRole(task.dispatch_parent_role)!==role) throw new Error('MCM_DISPATCH_DENIED: task parent role mismatch');
  if(task.project_root && await realpath(task.project_root)!==root) throw new Error('MCM_DISPATCH_DENIED: task belongs to another project');
  if(!Array.isArray(task.allowed_write_paths)||(!task.allowed_write_paths.length&&task.read_only!==true)) throw new Error('MCM_DISPATCH_DENIED: task needs explicit write scope or read_only');
  for(const path of task.allowed_write_paths) await projectPath(root,path,{missing:true,protectRaw:true});
  for(const dependency of task.depends_on??[]) { const record=tasks.find(row=>row.task_id===(typeof dependency==='string'?dependency:dependency?.task_id)); if(!record||record.status!=='approved') throw new Error('MCM_DISPATCH_DENIED: task dependency is not approved'); }
  const handover=task.handover??{};
  if(handover.from_agent_id || handover.source_refs?.length) {
    if(handover.permission_granted!==true || handover.reclaimed_at || !Number.isFinite(Date.parse(handover.permission_expires_at)) || Date.parse(handover.permission_expires_at)<=now) throw new Error('MCM_DISPATCH_DENIED: ownership handover missing, expired or reclaimed');
  }
  const inputs=task.inputs??[];
  if(!Array.isArray(inputs)) throw new Error('MCM_DISPATCH_DENIED: task inputs must be references');
  if(inputs.length) {
    const artifacts=envelope(await json(await projectPath(root,'.mcm/artifacts.json')),'artifacts'), seen=new Set();
    const check=async ref=>{
      const artifact=artifacts.find(row=>row.artifact_id===ref?.artifact_id);
      if(!artifact || artifact.version!==ref.version || artifact.sha256!==ref.sha256 || (ref.path!==undefined && ref.path!==artifact.path) || ['stale','retracted'].includes(artifact.status)||artifact.approval_state==='invalidated') throw new Error('MCM_DISPATCH_DENIED: invalid or stale task input reference');
      if(hash(await readFile(await projectPath(root,artifact.path)))!==ref.sha256) throw new Error('MCM_DISPATCH_DENIED: task input bytes changed');
      if(seen.has(artifact.artifact_id)) return; seen.add(artifact.artifact_id);
      for(const input of artifact.inputs??[]) await check(input);
    };
    for(const input of inputs) await check(input);
  }
  const chosen=snapshotPath??config.runtime_snapshot;
  if(typeof chosen!=='string'||!chosen) throw new Error('MCM_DISPATCH_DENIED: unknown Host capacity; runtime_snapshot is unset');
  const snapshot=await json(await projectPath(root,chosen));
  const capacity={...capacityOf(config,snapshot,now),snapshot_sha256:hash(snapshot)};
  if(!capacity.admit_one_task) throw new Error('MCM_DISPATCH_DENIED: admit_one_task=false; queue until actual release and fresh evidence');
  return {root,task_id:taskId,task_sha256:hash(task),args_sha256:hash(args),snapshot_path:chosen,capacity};
}

/** One process-local admission ledger. It is not a scheduler or a Host allocation oracle. */
export function createPermitLedger({now=()=>Date.now(),ttlMs=60000}={}) {
  const permits=new Map(), starts=[];
  const cleanup=capacity=>{
    const time=now(); for(const [key,p] of permits) if(p.expires_ms<=time) permits.delete(key);
    // A previously issued (including future-skew-tolerated) snapshot cannot
    // erase reservations it never observed. Require genuinely new evidence
    // captured strictly after admission and its original evidence, and never
    // use a timestamp still ahead of the tool clock to release a slot.
    for(let i=starts.length-1;i>=0;i--) {
      const entry=starts[i];
      if(capacity.snapshot_sha256 && entry.snapshot_sha256 && capacity.snapshot_sha256!==entry.snapshot_sha256 &&
        capacity.captured_ms>entry.started_ms && capacity.captured_ms>entry.snapshot_captured_ms && capacity.captured_ms<=time) starts.splice(i,1);
    }
  };
  const key=(sessionId,argsHash)=>`${sessionId}\0${argsHash}`;
  return {
    issue(sessionId,validation) {
      cleanup(validation.capacity);
      const k=key(sessionId,validation.args_sha256); permits.delete(k);
      if(validation.capacity.allocated+permits.size+starts.length>=validation.capacity.effective_normal_slots) throw new Error('MCM_DISPATCH_DENIED: current evidence plus outstanding dispatch reservations has no normal slot');
      const permit={...validation,session_id:sessionId,permit_id:randomUUID(),expires_ms:Math.min(now()+ttlMs,validation.capacity.captured_ms+60000)};
      permits.set(k,permit); return permit;
    },
    lookup(sessionId,args) { const permit=permits.get(key(sessionId,hash(args))); return permit && permit.expires_ms>now()?permit:undefined; },
    consume(sessionId,args,expected) {
      const k=key(sessionId,hash(args)), permit=permits.get(k);
      if(!permit||permit!==expected||permit.expires_ms<=now()) return false;
      permits.delete(k); starts.push({started_ms:now(),snapshot_captured_ms:permit.capacity.captured_ms,snapshot_sha256:permit.capacity.snapshot_sha256,session_id:sessionId,task_id:permit.task_id}); return true;
    },
    // Used only by tests/diagnostics, never a source of actual Host occupancy.
    pendingCount:()=>permits.size
  };
}
