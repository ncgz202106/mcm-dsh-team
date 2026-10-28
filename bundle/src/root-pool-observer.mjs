import { readFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join, isAbsolute, resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createRequire } from 'node:module';
import { hash } from './runtime-guard-core.mjs';

// Reference: public package bundles shipped in DSH 0.2.1-rc.2. These are
// version-specific internals, not a public allocator API or an OS boundary.
export const SOURCE_PIN = Object.freeze({
  version:'0.2.1-rc.2',
  desktop_host_entry_sha256:'6ae7cb9d57516b73c8aa4317c514ed81d28f2680efcee56d8faf2e588bb28c48',
  desktop_host_package_sha256:'e5dc6576213b8c888e3848a4956ef45bc64aa202cfc47ba93871db35b090251c',
  cordis_version:'4.0.5',
  cordis_bundle_sha256:'6a9394c0877ff45218818c6e815edd038f8057e1a1deb390a8d43ec81c57691e',
  cordis_package_sha256:'b73831b926b16cbd684aa1b277461e7800a2b35e2dd351ad3c2c8c0db158589d',
  subagents_bundle_sha256:'9a9572e70fffdb100deb63326167f32bbf63016ce49c0017495dabcb95b44168',
  agents_bundle_sha256:'7b59cf82c2784c25bdce4e3e24e5e5303b02b9f1003efacf50255492d17baf8b',
  service_class_sha256:'ed5c578643b2bfb22c2a43db8a2605c17f8c1685deb8d201371d662b1bc72205',
  manager_class_sha256:'00f79c8a19576ba8862362ca946eb9298492a62d69622286758bb6a85ba64763',
  pool_class_sha256:'7f3afb379c215094b908361d8296e4eac4f93b344347fbb2b2dce02d9b5a928f',
  registry_class_sha256:'10435104617d5ac2fcb536e354135fdae4fb643981f89f62d49bc40d23fc5a08'
});
const fnText=Function.prototype.toString;
const sourceText=value=>fnText.call(value);
const denied=reason=>{throw new Error(`MCM_CAPACITY_UNKNOWN: ${reason}`);};
const object=value=>value!==null&&(typeof value==='object'||typeof value==='function');
const MAX_ROWS=1024;
const ORIGINAL=Symbol.for('cordis.original');
// Official Cordis tracing returns a fresh service proxy on each access. The
// symbol only canonicalizes an injected value; it is never proof by itself.
// Raw classes and official module constructors are still checked below.
const original=value=>value?.[ORIGINAL]??value;

function checkClass(instance,expected,methods=[]) {
  if(!object(instance)) denied('missing runtime instance');
  const prototype=Object.getPrototypeOf(instance), ctor=prototype?.constructor;
  if(typeof ctor!=='function'||hash(sourceText(ctor))!==expected||instance.constructor!==ctor) denied('executing class differs from pinned source');
  const text=sourceText(ctor);
  for(const name of methods) {
    const descriptor=Object.getOwnPropertyDescriptor(prototype,name);
    if(Object.hasOwn(instance,name)||typeof descriptor?.value!=='function'||instance[name]!==descriptor.value||!text.includes(sourceText(descriptor.value))) denied('runtime method differs from pinned class');
  }
  return ctor;
}
function checkExecutingClasses(ctx) {
  const service=checkClass(original(ctx.subagents),SOURCE_PIN.service_class_sha256,['startActivation','requireManager']);
  const registry=checkClass(original(ctx.agents),SOURCE_PIN.registry_class_sha256,['get','roots','isOwnedBy']);
  checkClass(original(ctx.subagents).manager,SOURCE_PIN.manager_class_sha256,['materialize','rootPool','liveLineage','closingTeardownFor']);
  return {service,registry};
}

const SDK_PACKAGES=['@deepseek-ai/dsh-subagent','@deepseek-ai/dsh-agent','@deepseek-ai/cordis'];
// The desktop installs plugins outside its own node_modules ancestry. Resolve
// from its actual, hash-pinned Node-mode entry only if ordinary resolution is
// unavailable. This never launches the entry or imports an SDK module.
// Arguments are a module-level offline test seam, not tool/profile settings.
export async function resolveRuntimePackageUrls({
  resolveFromPlugin=name=>import.meta.resolve(name),argv=process.argv,read=readFile,
  resolveFromEntry=(entry,name)=>createRequire(pathToFileURL(entry)).resolve(name),pin=SOURCE_PIN
}={}) {
  try {
    return {origin:'plugin-resolution',urls:SDK_PACKAGES.map(name=>resolveFromPlugin(name))};
  } catch {
    const entry=argv?.[1],runtimeDir=argv?.[2];
    if(typeof entry!=='string'||typeof runtimeDir!=='string'||!isAbsolute(entry)||!isAbsolute(runtimeDir)||
      resolve(entry)!==resolve(runtimeDir,'node_modules','@deepseek-ai','dsh-desktop-host','lib','index.js')) denied('no supported actual desktop entry anchor');
    const packagePath=join(runtimeDir,'node_modules','@deepseek-ai','dsh-desktop-host','package.json');
    const [entryBytes,packageBytes]=await Promise.all([read(entry),read(packagePath)]);
    if(hash(entryBytes)!==pin.desktop_host_entry_sha256||hash(packageBytes)!==pin.desktop_host_package_sha256) denied('desktop entry/package source differs from pinned origin');
    const manifest=JSON.parse(packageBytes.toString('utf8'));
    if(manifest.name!=='@deepseek-ai/dsh-desktop-host'||manifest.version!==pin.version) denied('unsupported desktop entry manifest');
    const urls=SDK_PACKAGES.map(name=>{
      const path=resolveFromEntry(entry,name),expected=join(runtimeDir,'node_modules',...name.split('/'),'lib','index.js');
      if(typeof path!=='string'||!isAbsolute(path)||resolve(path)!==resolve(expected)) denied('desktop SDK origin differs from actual entry layout');
      return pathToFileURL(path).href;
    });
    return {origin:'pinned-desktop-host-entry',urls};
  }
}

/** Runs only when mounted inside the existing runtime. Never creates a Host. */
export async function verifyRuntimeSource(ctx) {
  const executing=checkExecutingClasses(ctx);
  const packages=[['@deepseek-ai/dsh-subagent',SOURCE_PIN.subagents_bundle_sha256,SOURCE_PIN.version],['@deepseek-ai/dsh-agent',SOURCE_PIN.agents_bundle_sha256,SOURCE_PIN.version],['@deepseek-ai/cordis',SOURCE_PIN.cordis_bundle_sha256,SOURCE_PIN.cordis_version]];
  const resolved=await resolveRuntimePackageUrls();
  const modules=[];
  for(const [index,[name,digest,version]] of packages.entries()) {
    const url=resolved.urls[index];
    if(!url.startsWith('file:')) denied('runtime package origin is not a local public module');
    const path=fileURLToPath(url), manifestBytes=await readFile(join(dirname(path),'..','package.json')),manifest=JSON.parse(manifestBytes.toString('utf8'));
    if(manifest.name!==name||manifest.version!==version||hash(await readFile(path))!==digest||
      (name==='@deepseek-ai/cordis'&&hash(manifestBytes)!==SOURCE_PIN.cordis_package_sha256)) denied('runtime version or resolved bundle SHA256 differs');
    // The existing official constructor must be the constructor of the actual
    // injected instance, not merely another copy found on disk.
    modules.push(await import(url));
  }
  if(modules[0].SubagentRuntime!==executing.service||(modules[1].AgentRegistry??modules[1].default)!==executing.registry) denied('resolved official module does not own injected service');
  checkExecutingClasses(ctx);
  return {pin:SOURCE_PIN,origin:resolved.origin,checkCurrent:()=>checkExecutingClasses(ctx),checkPool:pool=>checkClass(pool,SOURCE_PIN.pool_class_sha256,['reserve'])};
}

// Dependency injection is a module-level test seam, never a model/profile flag.
export function createRootPoolObserver({verifySource=verifyRuntimeSource,now=()=>Date.now(),maxAgeMs=60000}={}) {
  const captures=new Map(), domains=new WeakMap();
  const domainOf=(manager,root)=>{
    let roots=domains.get(manager);if(!roots){roots=new WeakMap();domains.set(manager,roots);}
    let id=roots.get(root);if(!id){id=randomUUID();roots.set(root,id);}return id;
  };
  const observe=(ctx,caller,source)=>{
    if(hash(source?.pin)!==hash(SOURCE_PIN)) denied('unsupported source pin');
    source.checkCurrent();
    const registry=original(ctx.agents),service=original(ctx.subagents),manager=service?.manager;
    if(!caller||typeof caller.id!=='string'||!caller.id||caller.id.length>256||registry?.get(caller.id)!==caller) denied('calling Agent is no longer the exact live instance');
    if(original(manager?.ctx?.agents)!==registry||!(manager.rootPools instanceof WeakMap)||!(manager.resident instanceof Map)||!(manager.materializations instanceof Set)||!(manager.closingScopes instanceof Map)||typeof manager.draining!=='boolean') denied('missing or unsupported manager binding');
    if(manager.draining) denied('manager is draining');
    if(manager.resident.size>MAX_ROWS||manager.materializations.size>MAX_ROWS||manager.closingScopes.size>MAX_ROWS) denied('observation exceeds bounded capacity coverage');
    const roots=registry.roots();
    if(!Array.isArray(roots)||roots.length>MAX_ROWS||roots.some(root=>!root||typeof root.id!=='string'||!root.id||root.id.length>256||registry.get(root.id)!==root)||new Set(roots).size!==roots.length) denied('runtime roots cannot be reconciled');
    const own=manager.resident.get(caller.id);
    let root,pool;const lineage=new Set([caller]);
    if(roots.includes(caller)) {
      if(own!==undefined) denied('runtime root also has resident ownership');
      root=caller;pool=manager.rootPools.get(root);
    } else {
      if(own?.kind!=='local'||own.handle?.agent!==caller) denied('manager is not an exact resident local Agent');
      pool=own.pool;
      const matches=roots.filter(candidate=>manager.rootPools.get(candidate)===pool);
      if(!object(pool)||matches.length!==1) denied('resident manager allocation root is unresolved');
      root=matches[0];
      let cursor=caller;const seen=new Set();
      while(cursor!==root) {
        if(seen.has(cursor)||seen.size>2) denied('resident ownership chain is inconsistent');
        seen.add(cursor);
        const activation=manager.resident.get(cursor.id),parent=activation?.parent;
        if(activation?.kind!=='local'||activation.handle?.agent!==cursor||activation.pool!==pool||!parent||registry.get(parent.id)!==parent||!registry.isOwnedBy(cursor.id,parent)) denied('resident ownership is not the exact shared-pool chain');
        cursor=parent;lineage.add(parent);
      }
    }
    for(const [closingRoot,members] of manager.closingScopes) {
      if(!(members instanceof Set)) denied('unsupported closing scope');
      if(lineage.has(closingRoot)||[...lineage].some(agent=>members.has(agent))) denied('calling allocation scope is closing');
    }
    const limit=service.config?.maxActiveSubagents?.get();
    if(!Number.isSafeInteger(limit)||limit<1) denied('configured per-pool limit is unknown');
    const relevantPending=[];
    for(const pending of manager.materializations) {
      if(!Array.isArray(pending?.lineage)||!pending.lineage.length) denied('unreconciled pending lineage');
      if(pending.lineage.includes(root)||pending.lineage.includes(caller)) relevantPending.push(pending);
    }
    const records=[],residents=[];
    if(pool!==undefined) {
      source.checkPool(pool);
      if(!(pool.slots instanceof Set)||pool.slots.size>MAX_ROWS) denied('unsupported pool reservation set');
    }
    for(const [id,activation] of manager.resident) {
      if(activation?.pool!==pool||pool===undefined) continue;
      if(typeof id!=='string'||!id||id.length>256||id!==activation.childId||!['local','external'].includes(activation.kind)||!(activation.ancestry instanceof WeakSet)||!activation.ancestry.has(root)||!activation.parent) denied('same-pool resident cannot be reconciled');
      if(activation.kind==='local'&&activation.handle?.agent?.id!==id) denied('local activation identity mismatch');
      records.push({agent_id:id,kind:activation.kind,closing:activation.closing!==undefined});
      residents.push([id,activation]);
    }
    records.sort((a,b)=>a.agent_id.localeCompare(b.agent_id));
    const slots=pool===undefined?[]:[...pool.slots];
    if(slots.some(slot=>typeof slot!=='symbol')) denied('unsupported reservation identity');
    // The pinned materialize implementation creates rootPool before reserve,
    // publishes into resident before deleting materializations, and releases
    // only after resident deletion. No absent-pool zero is inferred from a list.
    if(pool===undefined&&(manager.materializations.size!==0||manager.resident.has(root.id))) denied('absent-pool zero invariant is not proven');
    const gaps=[];
    if(relevantPending.length) gaps.push('own-pool-materialization-pending');
    if(slots.length!==records.length) gaps.push('reservations-not-reconciled-with-residents');
    if(new Set(records.map(row=>row.agent_id)).size!==records.length) gaps.push('duplicate-resident-identity');
    // Logical root domain survives first pool creation. Captures themselves
    // still bind the exact pool object, so replacement never reuses evidence.
    const domain=domainOf(manager,root);
    return {caller,root,registry,service,manager,pool,slots,residents,source,limit,domain,records,gaps,pending:relevantPending,
      absent_pool_zero_proven:pool===undefined};
  };
  const sameState=(a,b)=>a.caller===b.caller&&a.root===b.root&&a.registry===b.registry&&a.service===b.service&&a.manager===b.manager&&a.pool===b.pool&&a.limit===b.limit&&a.domain===b.domain&&
    hash(a.source.pin)===hash(b.source.pin)&&hash(a.records)===hash(b.records)&&a.slots.length===b.slots.length&&a.slots.every(slot=>b.slots.includes(slot))&&a.residents.length===b.residents.length&&a.residents.every(([id,value])=>b.residents.some(([otherId,other])=>id===otherId&&value===other))&&b.gaps.length===0;
  const cleanup=()=>{for(const [digest,entry] of captures) if(now()-entry.time>maxAgeMs) captures.delete(digest);};
  const current=(ctx,caller,snapshot,source)=>{
    cleanup();
    if(snapshot?.allocation_scope!=='root-activation-pool') denied('native dispatch requires root-activation-pool evidence');
    const digest=hash(snapshot),entry=captures.get(digest);
    if(!entry||entry.caller!==caller) denied('snapshot was not captured for this exact caller in this process');
    const state=observe(ctx,caller,source??entry.source);
    if(!sameState(entry,state)){captures.delete(digest);denied('allocation identity, source, limit or reservations changed; capture again');}
    return {allocation_domain_id:state.domain,root_agent_id:state.root.id,caller_agent_id:caller.id,source_verification:'process-local-capture-ledger'};
  };
  return {
    async capture(ctx,caller) {
      try {
        const source=await verifySource(ctx),state=observe(ctx,caller,source),time=now();cleanup();
        const snapshot={schema_version:1,capture_id:randomUUID(),captured_at:new Date(time).toISOString(),allocation_scope:'root-activation-pool',
          root_agent_id:state.root.id,caller_agent_id:caller.id,allocation_domain_id:state.domain,
          pool_capacity:{verified:state.gaps.length===0,max_active_descendants:state.limit,reserved_slots:state.slots.length,pending_materializations:state.pending.length,absent_pool_zero_proven:state.absent_pool_zero_proven},
          records:state.records.map(row=>({...row})),coverage_gaps:[...state.gaps],admit_one_task:state.gaps.length===0,
          source:{version:source.pin.version,subagents_bundle_sha256:source.pin.subagents_bundle_sha256,agents_bundle_sha256:source.pin.agents_bundle_sha256,
            module_origin:source.origin??'offline-test-injection',
            cordis_version:source.pin.cordis_version,cordis_bundle_sha256:source.pin.cordis_bundle_sha256,
            verification:'resolved-official-constructors+executed-class-fingerprints+disk-bundle-sha256',
            limitation:'Does not attest every loaded closure helper or provide OS isolation.'}};
        if(!state.gaps.length){if(captures.size>=128)captures.delete(captures.keys().next().value);captures.set(hash(snapshot),{...state,time});}
        return {capacity_known:state.gaps.length===0,snapshot,writes_project:false,creates_or_resumes_agent:false};
      } catch(error) {
        return {capacity_known:false,allocation_scope:'root-activation-pool',reason:String(error.message??error).slice(0,600),writes_project:false,creates_or_resumes_agent:false};
      }
    },
    async verify(ctx,caller,snapshot) {return current(ctx,caller,snapshot,await verifySource(ctx));},
    assertCurrent(ctx,caller,snapshot) {return current(ctx,caller,snapshot);}
  };
}
