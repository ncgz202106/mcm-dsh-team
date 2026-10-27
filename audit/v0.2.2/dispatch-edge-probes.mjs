import {mkdtemp,mkdir,writeFile,readFile,link,rm,realpath} from 'node:fs/promises';
import {join,resolve,relative,sep} from 'node:path';
import {tmpdir} from 'node:os';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const candidate=resolve(process.argv[2]);
const {validateDispatch,hash}=await import(pathToFileURL(join(candidate,'bundle/src/runtime-guard-core.mjs')));
const {apply}=await import(pathToFileURL(join(candidate,'bundle/src/runtime-guard-plugin.mjs')));
const results=[];
async function fixture(){
 const root=await realpath(await mkdtemp(join(tmpdir(),'mcm-independent-offline-')));
 const save=async(p,v)=>{await mkdir(join(root,p,'..'),{recursive:true});await writeFile(join(root,p),JSON.stringify(v));};
 await mkdir(join(root,'.mcm-project'));await mkdir(join(root,'candidate'));await mkdir(join(root,'review'));
 const a={artifact_id:'A',path:'candidate/a.txt',version:1,sha256:hash('a'),status:'draft',approval_state:'draft',task_id:'AUTHOR',author_agent_id:'author-id',inputs:[]};
 const upstream={artifact_id:'U',path:'candidate/u.txt',version:1,sha256:hash('u'),status:'verified',inputs:[]};
 a.inputs=[{artifact_id:'U',path:upstream.path,version:1,sha256:upstream.sha256}];
 const ref={artifact_id:'A',path:a.path,version:1,sha256:a.sha256};
 const producer={task_id:'AUTHOR',owner_agent_id:'author-id',status:'in_review',project_root:'.',outputs:[structuredClone(ref)],output_readback:[structuredClone(ref)],completion_handoff_path:'candidate/handoff.txt'};
 const t={task_id:'REVIEW',owner_role:'mcm-reviewer',owner_agent_id:'pending:child',status:'queued',acceptance_criteria:['Independent check'],allowed_write_paths:['review'],inputs:[ref],depends_on:[{task_id:'AUTHOR',relation:'review',output_refs:[ref],handoff_ref:{path:producer.completion_handoff_path,sha256:hash('delivered')}}]};
 const config={normal_slots:7,reserve_slots:1,pause_state:{paused:false},runtime_snapshot:'unit-test-capacity.json'};
 const snapshot={captured_at:new Date().toISOString(),allocation_scope:'host',host_capacity:{verified:true,max_active_descendants:8,evidence_ref:'SYNTHETIC-OFFLINE-UNIT-TEST-ONLY-NOT-LIVE'},records:[]};
 for(const [p,v] of [[a.path,'a'],[upstream.path,'u'],[producer.completion_handoff_path,'delivered']])await writeFile(join(root,p),v);
 const sync=async()=>{await save('.mcm/tasks.json',{format_version:1,records:[t,producer]});await save('.mcm/artifacts.json',{format_version:1,records:[a,upstream]});await save('config/runtime.json',config);await save('unit-test-capacity.json',snapshot);};await sync();
 const args={cwd:root,agent_preset:'mcm-reviewer',description:'offline unit review',prompt:'Read only fixed candidate; fixture only'};
 return {root,t,a,upstream,producer,ref,config,snapshot,sync,save,args,request:{root,role:'mcm-captain',depth:0,args,taskId:t.task_id}};
}
async function run(name,fn){let f;try{f=await fixture();await fn(f);results.push({name,pass:true});}catch(e){results.push({name,pass:false,error:String(e.stack??e)});}finally{if(f){const actual=await realpath(f.root);const rel=relative(await realpath(tmpdir()),actual);assert(!rel.startsWith('..')&&!rel.includes(sep+'..'+sep)&&actual.includes('mcm-independent-offline-'));await rm(actual,{recursive:true});}}}
await run('valid review is read-only and local capacity does not make a real claim',async f=>{const before=await readFile(join(f.root,'.mcm/tasks.json'));assert((await validateDispatch(f.request)).evidence_sha256);assert.deepEqual(await readFile(join(f.root,'.mcm/tasks.json')),before);});
await run('legacy approved object dependency accepts and delivered-only execution rejects',async f=>{f.t.depends_on=[{task_id:'AUTHOR'}];await f.sync();await assert.rejects(validateDispatch(f.request),/not approved/);f.producer.status='approved';await f.sync();await validateDispatch(f.request);});
await run('legacy readback without version and declared outputs without optional pins accepts',async f=>{delete f.producer.output_readback[0].version;f.producer.outputs=[{artifact_id:'A',path:f.ref.path}];await f.sync();await validateDispatch(f.request);});
await run('null relation and boolean review ref version deny',async f=>{f.t.depends_on[0].relation=null;await f.sync();await assert.rejects(validateDispatch(f.request),/relation/);f.t.depends_on[0].relation='review';f.ref.version=true;await f.sync();await assert.rejects(validateDispatch(f.request),/complete output/);});
await run('metadata-only upstream revision changes fingerprint while task pin and bytes stay fixed',async f=>{const first=await validateDispatch(f.request);f.upstream.audit_revision={nested:'new'};await f.sync();const second=await validateDispatch(f.request);assert.equal(first.task_sha256,second.task_sha256);assert.notEqual(first.evidence_sha256,second.evidence_sha256);});
await run('boolean optional producer output and readback pins deny',async f=>{f.producer.output_readback[0].version=true;await f.sync();await assert.rejects(validateDispatch(f.request),/readback/);f.producer.output_readback[0].version=1;f.producer.outputs[0].version=true;await f.sync();await assert.rejects(validateDispatch(f.request),/declared/);});
await run('explicit read-only review with no writable paths accepts',async f=>{f.t.read_only=true;f.t.allowed_write_paths=[];await f.sync();await validateDispatch(f.request);});
await run('unknown capacity still denies valid delivered review',async f=>{f.config.runtime_snapshot=null;await f.sync();await assert.rejects(validateDispatch(f.request),/runtime_snapshot is unset/);});
for(const stage of ['tools/pre-execute','tools/execute'])await run('nested upstream metadata mutation denied at '+stage,async f=>{
 const callbacks={},tools=new Map();let guard;
 const agent={id:f.root,ctx:{},session:{header:{cwd:f.root,delegationDepth:0}}};
 apply({tools:{register:x=>tools.set(x.name,x),guard:x=>{guard=x;}},on:(name,fn)=>{callbacks[name]=fn;},agentPresets:{composedPreset:()=> 'mcm-captain'},subagents:{config:{maxActiveSubagents:{get:()=>8}}}},{role:'mcm-captain'});
 await tools.get('mcm_dispatch_preflight').execute({task_id:'REVIEW',subagent_arguments:f.args},{agent});
 const exec={agent,name:'subagent',arguments:structuredClone(f.args)};
 if(stage==='tools/execute'){await callbacks['tools/pre-execute'](exec,async()=>{});assert.equal(guard(exec),undefined);}
 f.upstream.extra_nested={revision:2};await f.sync();let bodies=0;await assert.rejects(callbacks[stage](exec,async()=>{bodies++;}),/source evidence|dispatch state/);assert.equal(bodies,0);
});
// Observational edge: physical hard links are distinct from path/junction aliases.
await run('hardlink overlap diagnostic',async f=>{await link(join(f.root,f.a.path),join(f.root,'review/source-hardlink.txt'));const outcome=await validateDispatch(f.request);assert(outcome.evidence_sha256);results.push({name:'hardlink protection observation',classification:'limitation',admitted:true,description:'Writable review path can contain a hardlink to source; normalized-path protection does not compare physical file identity. No fixture source bytes were modified.'});});
console.log(JSON.stringify({scope:'Synthetic offline fixtures and mocked tool callbacks only; no Host, DSH, API, spawn or native child used',results},null,2));
if(results.some(x=>x.pass===false))process.exitCode=1;
