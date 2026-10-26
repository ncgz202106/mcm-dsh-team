import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';

export const name = 'mcm-native-smoke';
export const inject = ['agents', 'agentPresets', 'tools', 'llm', 'subagents', 'sessions', 'sessionQuery', 'sessionPersistence', 'sessionProjections'];

export function apply(ctx, config) {
  const run = async () => {
    await ctx.get('loader')?.await();
    for (const [path, expected] of Object.entries(config.fingerprints)) assert.equal(createHash('sha256').update(await readFile(join(config.bundlePath, path))).digest('hex'), expected, `Bundle changed before fixture: ${path}`);
    const load = (pkg) => import(pathToFileURL(join(config.runtimeRoot, 'node_modules', '@deepseek-ai', pkg, 'lib', 'index.js')).href);
    const { LlmAdapter, createUserMessage } = await load('dsh-llm');
    const { scopeOf } = await load('dsh-scope');
    const checks = [];
    const requests = [];
    const rootIds = new Set();
    const release = new Map();
    const unheld = new Set();
    let holdChildren = false;
    const archiveActions = new Set();
    class Scripted extends LlmAdapter {
      async resolveModel(provider, model) { return { provider, id: model, name: model, contextWindow: 128000, inputModalities: ['text'] }; }
      async *stream(request) {
        requests.push({ session_id: request.sessionId, provider: request.provider, model: request.model, tools: request.tools?.map((tool) => tool.name) ?? [], messages: request.messages });
        if (holdChildren && !rootIds.has(request.sessionId) && !unheld.has(request.sessionId)) await new Promise((done) => release.set(request.sessionId, done));
        const text = request.messages.flatMap((message) => message.content ?? []).filter((block) => block.type === 'text').map((block) => block.text).join('\n');
        if ((text.includes('SMOKE_PTC_ARCHIVE') || text.includes('SMOKE_FIGURE_RUNTIME') || text.includes('SMOKE_EVIDENCE_RUNTIME')) && !archiveActions.has(request.sessionId)) {
          archiveActions.add(request.sessionId);
          let code = "return await tools.mcm_archive_audit({checkpoint:'native-smoke',purpose:'Synthetic isolated real-runtime verification'})";
          const quote = (s) => `'${s.replaceAll("'", "''")}'`;
          if (text.includes('SMOKE_FIGURE_RUNTIME')) code = `const skill = await tools.skill({name:'nature-figure'}); const run = await tools.pwsh(${JSON.stringify({description:'Generate four synthetic scientific figures using installed skill guidance',command:`& ${quote(config.python)} scripts/figure_demo.py --root . --skill-root ${quote(join(config.skillRoot,'nature-figure'))}`,workdir:config.project,timeoutMs:90000})}); return {skill,run};`;
          if (text.includes('SMOKE_EVIDENCE_RUNTIME')) code = `const search = await tools.skill({name:'nature-academic-search'}); const verify = await tools.skill({name:'nature-ref-verifier'}); const run = await tools.pwsh(${JSON.stringify({description:'Public metadata search and DOI field verification; no credentials or full text',command:`& ${quote(config.python)} scripts/public-source-probe.py --skill-root ${quote(config.skillRoot)}`,workdir:config.project,timeoutMs:90000})}); return {search,verify,run};`;
          const block = { type: 'tool-call', id: `fixture-${request.sessionId}`, name: 'run_code', arguments: JSON.stringify({ code, description: 'Exercise real PTC and installed task-specific tools' }) };
          yield { type: 'block-start', index: 0, blockType: 'tool-call' };
          yield { type: 'block-end', index: 0, block };
        } else {
          yield { type: 'block-start', index: 0, blockType: 'text' };
          yield { type: 'text-delta', index: 0, text: `Synthetic response for ${request.sessionId}` };
          yield { type: 'block-end', index: 0, block: { type: 'text', text: `Synthetic response for ${request.sessionId}` } };
        }
        yield { type: 'finish', reason: { kind: 'stop' } };
      }
    }
    ctx.llm.registerAdapter(['mcm-smoke'], new Scripted());
    const declared = await ctx.agentPresets.list();
    try { const auditModule = await import(pathToFileURL(join(config.bundlePath,'src/archive-plugin.mjs')).href); await writeFile(join(config.work, 'audit-module.json'), JSON.stringify({ exports: Object.keys(auditModule), inject: auditModule.inject })); }
    catch (error) { await writeFile(join(config.work, 'audit-module-error.txt'), error.stack ?? String(error)); throw error; }
    await writeFile(join(config.work, 'service-presence.json'), JSON.stringify(Object.fromEntries(['tools', 'sessions', 'sessionQuery', 'sessionPersistence', 'sessionProjections', 'fs', 'workingDirectory'].map((key) => [key, Boolean(ctx.get(key))])), null, 2));
    await writeFile(join(config.work, 'preset-inventory.json'), JSON.stringify(await ctx.agentPresets.compositionInventory(), null, 2));
    const ids = declared.filter((preset) => preset.id.startsWith('mcm-')).map((preset) => preset.id);
    assert.equal(ids.length, 12);
    checks.push({ name: 'native_registry_12_presets', passed: true, presets: ids });
    const handles = new Map();
    const observations = [];
    const tick = () => new Promise((done) => setTimeout(done, 10));
    const waitFor = async (predicate, title) => { const until = Date.now() + 10000; while (!predicate()) { if (Date.now() > until) throw new Error(`Timed out: ${title}`); await tick(); } };
    for (const id of ids) {
      const sessionId = `smoke-${id}`;
      rootIds.add(sessionId);
      const handle = await ctx.agents.create({ sessionId, meta: { cwd: config.project, agentPreset: id }, agentOptions: { provider: 'mcm-smoke', model: 'scripted' }, setup: async (agentCtx) => { await ctx.agentPresets.mount(agentCtx, id); } });
      handles.set(id, handle);
      const agent = handle.agent;
      const scope = scopeOf(agent.ctx);
      const sdk = ctx.tools.sdkSchemas(scope).map((tool) => tool.name);
      const wire = ctx.tools.wireSchemas(scope).schemas.map((tool) => tool.name);
      assert.deepEqual(wire, ['run_code']);
      assert.ok(sdk.includes('send_message'));
      assert.equal(sdk.includes('subagent'), ['mcm-captain', 'mcm-model-lead', 'mcm-paper-lead', 'mcm-code-lead'].includes(id));
      assert.equal(sdk.includes('mcm_archive_audit'), id === 'mcm-captain');
      assert.equal(sdk.includes('ask_user_question'), id === 'mcm-captain');
      agent.followup(createUserMessage({ content: [{ type: 'text', text: `SYNTHETIC_ROLE_SMOKE ${id}` }], source: { kind: 'user' } }));
      await agent.whenIdle();
      const sent = requests.find((request) => request.session_id === sessionId);
      assert.ok(sent, `No real model-service request for ${id}`);
      assert.deepEqual(sent.tools, ['run_code']);
      const system = sent.messages.filter((message) => message.role === 'system').flatMap((message) => message.content ?? []).filter((block) => block.type === 'text').map((block) => block.text).join('\n');
      assert.ok(system.includes('run_code'));
      assert.ok(system.includes('send_message'));
      if (id === 'mcm-captain') assert.equal(system.includes('You are in plan mode. Stay in plan mode until'), false);
      observations.push({ preset: id, actual_wire_tools: wire, sdk_tool_count: sdk.length, sdk_tools: sdk });
      if (id !== 'mcm-captain') await handle.dispose();
    }
    checks.push({ name: 'native_preset_mount_and_generated_ptc_sdk', passed: true, roles: observations });
    checks.push({ name: 'captain_native_plan_defaults_to_execution', passed: true });
    const captain = handles.get('mcm-captain').agent;
    const exec = (agent, callId) => ({ agent, callId, signal: new AbortController().signal });
    const tool = (agent, name) => ctx.tools.get(name, scopeOf(agent.ctx));
    holdChildren = true;
    const leadStart = await tool(captain, 'subagent').execute({ description: 'Synthetic model lead', prompt: 'Hold for native routing checks', agent_preset: 'mcm-model-lead', cwd: config.project }, exec(captain, 'native-spawn-lead'));
    const leadId = leadStart.subagentId;
    await waitFor(() => ctx.agents.get(leadId), 'lead publication');
    const lead = ctx.agents.get(leadId);
    const leafStart = await tool(lead, 'subagent').execute({ description: 'Synthetic modeler', prompt: 'Hold for depth check', agent_preset: 'mcm-modeler', cwd: config.project }, exec(lead, 'native-spawn-leaf'));
    const leafId = leafStart.subagentId;
    await waitFor(() => ctx.agents.get(leafId), 'leaf publication');
    const leaf = ctx.agents.get(leafId);
    assert.equal(lead.session.header.delegationDepth, 1);
    assert.equal(leaf.session.header.delegationDepth, 2);
    assert.equal(ctx.agentPresets.composedPreset(lead.ctx), 'mcm-model-lead');
    assert.equal(ctx.agentPresets.composedPreset(leaf.ctx), 'mcm-modeler');
    assert.equal(tool(leaf, 'subagent'), undefined);
    await assert.rejects(tool(lead, 'subagent').execute({ description: 'Forbidden depth3', prompt: 'must fail', agent_preset: 'mcm-modeler', cwd: config.project }, exec(leaf, 'native-depth-rejection')), /depth .*exceeds|maxDepth/i);
    await tool(captain, 'send_message').execute({ agent_id: leadId, message: 'Synthetic parent-to-child routing check' }, exec(captain, 'native-down-message'));
    await tool(lead, 'send_message').execute({ agent_id: captain.id, message: 'Synthetic child-to-parent routing check' }, exec(lead, 'native-up-message'));
    await assert.rejects(tool(captain, 'send_message').execute({ agent_id: leafId, message: 'Non-adjacent target must fail' }, exec(captain, 'native-grandchild-rejection')), /direct|adjacent|authorized|send|target|parent/i);
    checks.push({ name: 'native_spawn_depth2_and_adjacent_message_controls', passed: true, lead: leadId, leaf: leafId, third_level_rejected: true, non_adjacent_message_rejected: true, invocation: 'Real installed tool execute methods; scheduler bypassed only for these controlled conformance calls.' });
    holdChildren = false;
    for (const done of release.values()) done();
    release.clear();
    while (true) { await captain.whenIdle(); const before = captain.session.seq; if (!await ctx.subagents.waitForChildren(captain) && captain.status === 'idle' && before === captain.session.seq) break; }
    captain.followup(createUserMessage({ content: [{ type: 'text', text: 'SMOKE_PTC_ARCHIVE' }], source: { kind: 'user' } }));
    await captain.whenIdle();
    await ctx.sessions.flush(captain.session);
    const reader = await ctx.sessionPersistence.open(captain.id, 'read');
    let events;
    try { events = (await reader.read(0)).events; } finally { await reader.close(); }
    await writeFile(join(config.work, 'captain-events.json'), JSON.stringify(events, null, 2));
    const archiveResults = events.filter((event) => event.type === 'tool/result' && (event.data.message?.content ?? []).some((block) => block.type === 'text' && block.text.includes('"transcripts_complete"') && block.text.includes('"archived_sessions"')));
    assert.ok(archiveResults.length, 'No successful archive result from real run_code execution');
    const nested = events.filter((event) => event.type === 'tool/ptc-dispatch-start' && event.data.name === 'mcm_archive_audit');
    assert.ok(nested.length, 'Real nested PTC archive call was not logged');
    const resultText = archiveResults[0].data.message.content.find((block) => block.type === 'text').text;
    const archiveOutput = JSON.parse(resultText.slice(resultText.indexOf('{'), resultText.lastIndexOf('}') + 1));
    assert.equal(archiveOutput.transcripts_complete, true);
    assert.equal(archiveOutput.archived_sessions, 3);
    const savedManifest = JSON.parse(await readFile(join(archiveOutput.directory, 'manifest.json'), 'utf8'));
    assert.equal(savedManifest.archived_sessions, 3);
    checks.push({ name: 'native_ptc_execution_and_archive_public_api_write', passed: true, native_nested_archive_calls: nested.length, native_archive_result_count: archiveResults.length, archived_sessions: savedManifest.archived_sessions, archive_directory: archiveOutput.directory });
    await handles.get('mcm-captain').dispose();
    // A separate native tree keeps the three-session archive test unambiguous.
    const capacityRootId = 'smoke-capacity-captain';
    rootIds.add(capacityRootId);
    const capacityHandle = await ctx.agents.create({ sessionId: capacityRootId, meta: { cwd: config.project, agentPreset: 'mcm-captain' }, agentOptions: { provider: 'mcm-smoke', model: 'scripted' }, setup: async (agentCtx) => { await ctx.agentPresets.mount(agentCtx, 'mcm-captain'); } });
    const capacityRoot = capacityHandle.agent;
    holdChildren = true;
    const start = async (parent, preset, label) => {
      const value = await tool(parent, 'subagent').execute({ description: label, prompt: `Synthetic held work: ${label}`, agent_preset: preset, cwd: config.project }, exec(parent, label));
      await waitFor(() => Boolean(ctx.agents.get(value.subagentId)) && release.has(value.subagentId), `${label} started`);
      return value.subagentId;
    };
    const capacityLeadId = await start(capacityRoot, 'mcm-model-lead', 'capacity-lead');
    const capacityLead = ctx.agents.get(capacityLeadId);
    const capacityLeafId = await start(capacityLead, 'mcm-modeler', 'capacity-leaf');
    unheld.add(capacityLeadId);
    release.get(capacityLeadId)();
    await waitFor(() => capacityLead.status === 'idle', 'leader idle while owning held descendant');
    assert.ok(ctx.agents.get(capacityLeadId), 'Waiting supervisor must remain resident while its descendant is active');
    const regular = [];
    for (let index = 0; index < 5; index++) regular.push(await start(capacityRoot, 'mcm-evidence', `regular-${index + 3}`));
    const atSeven = 2 + regular.length;
    assert.equal(atSeven, 7);
    // This queue belongs to the fixture scheduler; DSH itself does not enqueue rejected starts.
    const pendingTasks = [{ preset: 'mcm-evidence', label: 'fixture-deferred-normal-task' }];
    const emergencyId = await start(capacityRoot, 'mcm-evidence', 'emergency-slot-8');
    const childrenBeforeRejection = await ctx.subagents.listChildren(capacityRoot.id);
    let rejectedCode;
    await assert.rejects(tool(capacityRoot, 'subagent').execute({ description: 'capacity-probe-9', prompt: 'Must not be queued by Host', agent_preset: 'mcm-evidence', cwd: config.project }, exec(capacityRoot, 'capacity-probe-9')), (error) => {
      rejectedCode = error.code;
      return error.code === 'ACTIVATION_LIMIT_REACHED';
    });
    assert.equal((await ctx.subagents.listChildren(capacityRoot.id)).length, childrenBeforeRejection.length);
    const releasedId = regular[0];
    release.get(releasedId)();
    await waitFor(() => !ctx.agents.get(releasedId), 'completed child disposed and slot reclaimed');
    await tick();
    assert.equal((await ctx.subagents.listChildren(capacityRoot.id)).length, childrenBeforeRejection.length, 'Host must not automatically start the rejected ninth task');
    const pending = pendingTasks.shift();
    const resumedId = await start(capacityRoot, pending.preset, pending.label);
    checks.push({ name: 'native_capacity_7_plus_1_then_reclaim', passed: true,
      host_capacity_override: false, observed_child_capacity: 8, root_excluded: true, idle_waiting_supervisor_counted: true,
      normal_active_before_emergency: atSeven, emergency_slot_8: emergencyId, ninth_admission_error: rejectedCode,
      host_automatically_queued_rejection: false, fixture_queue_length_after_explicit_dequeue: pendingTasks.length,
      reclaimed_child: releasedId, explicitly_started_after_reclaim: resumedId,
      waiting_supervisor: capacityLeadId, held_descendant: capacityLeafId,
      queue_owner: 'The fixture scheduler explicitly stores/dequeues one pending task; no production scheduler or Host capacity setting was changed.' });
    holdChildren = false;
    for (const done of release.values()) done();
    release.clear();
    while (true) { await capacityRoot.whenIdle(); const before = capacityRoot.session.seq; if (!await ctx.subagents.waitForChildren(capacityRoot) && capacityRoot.status === 'idle' && before === capacityRoot.session.seq) break; }
    await capacityHandle.dispose();
    // Separate role tree: actual native role binding and actual PTC skill/tool calls.
    const specialistRootId = 'smoke-specialist-captain'; rootIds.add(specialistRootId);
    const specialistHandle = await ctx.agents.create({sessionId:specialistRootId,meta:{cwd:config.project,agentPreset:'mcm-captain'},agentOptions:{provider:'mcm-smoke',model:'scripted'},setup:async(c)=>{await ctx.agentPresets.mount(c,'mcm-captain');}});
    const specialistRoot = specialistHandle.agent;
    holdChildren = true;
    const codeLeadId = await start(specialistRoot,'mcm-code-lead','optional-code-lead');
    const codeLead = ctx.agents.get(codeLeadId);
    const programmers = [await start(codeLead,'mcm-programmer','solver-instance'), await start(codeLead,'mcm-programmer','experiment-instance')];
    for (const id of programmers) {assert.equal(ctx.agentPresets.composedPreset(ctx.agents.get(id).ctx),'mcm-programmer');assert.equal(ctx.agents.get(id).session.header.delegationDepth,2);}
    checks.push({name:'native_optional_code_lead_two_programmers',passed:true,lead:codeLeadId,programmers,default_start_enabled:false});
    holdChildren=false;for(const done of release.values())done();release.clear();
    while(true){await specialistRoot.whenIdle();const before=specialistRoot.session.seq;if(!await ctx.subagents.waitForChildren(specialistRoot)&&specialistRoot.status==='idle'&&before===specialistRoot.session.seq)break;}
    // Keep paper lead alive while inspecting the actual child's preset before it completes.
    holdChildren=true;
    const paperLeadId=await start(specialistRoot,'mcm-paper-lead','paper-lead');const paperLead=ctx.agents.get(paperLeadId);
    const figureStart=await tool(paperLead,'subagent').execute({description:'Quantitative figure specialist',prompt:'SMOKE_FIGURE_RUNTIME',agent_preset:'mcm-figure',cwd:config.project},exec(paperLead,'spawn-figure'));
    await waitFor(()=>release.has(figureStart.subagentId),'figure held');
    assert.equal(ctx.agentPresets.composedPreset(ctx.agents.get(figureStart.subagentId).ctx),'mcm-figure');
    assert.ok((await ctx.subagents.listChildren(paperLeadId)).some(child=>(child.subagentId??child.id)===figureStart.subagentId),'Figure must be published under paper lead');
    holdChildren=false;for(const done of release.values())done();release.clear();
    while(true){await specialistRoot.whenIdle();const before=specialistRoot.session.seq;if(!await ctx.subagents.waitForChildren(specialistRoot)&&specialistRoot.status==='idle'&&before===specialistRoot.session.seq)break;}
    const readEvents=async(id)=>{const reader=await ctx.sessionPersistence.open(id,'read');try{return(await reader.read(0)).events;}finally{await reader.close();}};
    const figureEvents=await readEvents(figureStart.subagentId);
    for(const name of ['skill','pwsh'])assert.ok(figureEvents.some(e=>e.type==='tool/ptc-dispatch-start'&&e.data.name===name),`Figure did not execute ${name}`);
    const figureManifest=JSON.parse(await readFile(join(config.project,'figures/figure-demo/demo-manifest.json'),'utf8'));
    checks.push({name:'native_paper_lead_figure_skill_real_outputs',passed:true,paper_lead:paperLeadId,figure:figureStart.subagentId,manifest:join(config.project,'figures/figure-demo/demo-manifest.json'),manifest_sha256:createHash('sha256').update(await readFile(join(config.project,'figures/figure-demo/demo-manifest.json'))).digest('hex'),skill_read_through_native_tool:true,quantitative_outputs_generated_by_native_pwsh:true});
    const evidenceStart=await tool(specialistRoot,'subagent').execute({description:'Public source evidence specialist',prompt:'SMOKE_EVIDENCE_RUNTIME',agent_preset:'mcm-evidence',cwd:config.project},exec(specialistRoot,'spawn-evidence'));
    while(true){await specialistRoot.whenIdle();const before=specialistRoot.session.seq;if(!await ctx.subagents.waitForChildren(specialistRoot)&&specialistRoot.status==='idle'&&before===specialistRoot.session.seq)break;}
    const evidenceEvents=await readEvents(evidenceStart.subagentId);
    assert.equal(evidenceEvents.filter(e=>e.type==='tool/ptc-dispatch-start'&&e.data.name==='skill').length,2);
    const sourceProbe=JSON.parse(await readFile(join(config.project,'evidence/public-source-probe.json'),'utf8'));
    assert.equal(sourceProbe.passed,true);
    checks.push({name:'native_evidence_skill_and_public_metadata_probe',passed:true,agent:evidenceStart.subagentId,probe:sourceProbe});
    await specialistHandle.dispose();
    const runtime = JSON.parse(await readFile(join(config.runtimeRoot, 'node_modules', '@deepseek-ai', 'dsh', 'package.json'), 'utf8'));
    const provenance = JSON.parse(await readFile(join(config.bundlePath, 'provenance.json'), 'utf8'));
    const guardBytes=await readFile(config.guardReportPath);
    const guardReport=JSON.parse(guardBytes.toString('utf8'));
    assert.equal(guardReport.status,'passed','Current guard PTC pipeline report must pass before baseline report publication');
    assert.ok(guardReport.checks.length>=6&&guardReport.checks.every(check=>check.passed===true));
    assert.equal(guardReport.launcher_sha256,config.launcherSha256,'Guard report must use this launcher byte version');
    for(const[path,expected]of Object.entries(config.fingerprints))assert.equal(guardReport.bundle_file_sha256[path],expected,`Guard evidence source drift: ${path}`);
    for (const [path, expected] of Object.entries(config.fingerprints)) assert.equal(createHash('sha256').update(await readFile(join(config.bundlePath, path))).digest('hex'), expected, `Bundle changed during fixture: ${path}`);
    const report = { schema_version: 1, status: 'passed', executed_at: new Date().toISOString(), runtime_version: runtime.version,
      bundle_source:config.bundlePath,bundle_file_sha256: config.fingerprints, prompt_sha256: provenance.prompt_sha256,
      fixture_sha256:config.fixtureSha256,launcher_sha256:config.launcherSha256,
      guard_report:{path:config.guardReportPath,sha256:createHash('sha256').update(guardBytes).digest('hex'),checks:guardReport.checks.length,scope:'Independent real model-stream -> run_code -> nested-tool pre-execute/monotonic guard. Baseline direct native API conformance calls below do not prove this guard.'},
      loading: 'Desktop bundled Electron in Node mode, native headless profile cloned into isolated DSH_HOME, actual bundle linked only inside the isolated profile.',
      isolation: { work: config.work, project: config.project, credentials_read: false, external_model_calls: false, user_profile_modified: false, live_desktop_modified: false },
      real_components: ['Cordis loader', 'DSH agent preset registry and activation audits', 'all twelve role plugin trees', 'generated PTC SDK and wire schemas', 'native agent loop and session persistence', 'native spawn service and depth validation', 'native parent-child message tools', 'native run_code Node runtime', 'MCM archive plugin using native persistence/query/fs services', 'native skill reader, pwsh, Python figure generation and public metadata fetch'],
      simulated_components: ['Only LLM provider output is generated by an in-process deterministic Scripted adapter; no scientific quality or award claim is tested.'], checks,
      limits: ['This is an isolated actual-runtime test, not installation into the user running desktop Host.', 'Controlled spawn/control conformance calls invoke installed tool execute methods directly; final archive call goes through the real model-stream -> run_code -> nested-tool path.', 'The Windows runtime reported partial file sandbox enforcement in its run_code result; this test does not certify OS sandbox isolation.'] };
    await writeFile(config.reportPath, JSON.stringify(report, null, 2) + '\n');
    ctx.get('appExit')(0);
  };
  run().catch(async (error) => { console.error(error.stack ?? String(error)); try { await writeFile(join(config.work, 'fixture-error.txt'), error.stack ?? String(error)); } finally { ctx.get('appExit')(1); } });
}
