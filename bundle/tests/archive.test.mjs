import test from 'node:test';
import assert from 'node:assert/strict';
import { collectAudit, visibleValue, redactText } from '../src/archive-core.mjs';
import { createAuditTool } from '../src/archive-tool.mjs';
import { resolve } from 'node:path';

const event = (seq, type, data) => ({ seq, type, time: 1000 + seq, data });
const message = (text) => ({ role: 'user', content: [{ type: 'text', text }] });
const local = (id, children = []) => ({ session: { header: { id } }, descendants: children });

function fixture({ failRead, failFlush, failClose, failLineage = false } = {}) {
  const records = {
    captain: { header: { id: 'captain', cwd: '/project', agentPreset: 'standard' }, events: [
      event(0, 'agent-preset/selected', { agentPreset: 'mcm-captain' }),
      event(1, 'system/message', { turn: 1, step: 1, message: { role: 'system', content: [{ type: 'text', text: 'Shared rules and role' }] } }),
      event(2, 'request/context', { provider: 'provider-a', model: 'model-a' }),
      event(3, 'request/header', { header: { config: { apiKey: 'do-not-export', maxTokens: 2000 }, tools: [{ name: 'run_code' }] } }),
      event(4, 'user/message', message('Build model from these inputs. api_key="credential-value"')),
      event(5, 'tool/call', { turn: 1, step: 1, callId: 'ptc-1', name: 'run_code', arguments: { description: 'Delegate independent models', code: 'return await tools.subagent(...)' } }),
      event(6, 'tool/call', { turn: 1, step: 1, callId: 'ptc-1:ptc:1', name: 'subagent', arguments: { description: 'Model lead', agent_preset: 'mcm-model-lead' } }),
      event(7, 'tool/result', { turn: 1, step: 1, message: { role: 'tool', callId: 'ptc-1:ptc:1', content: [{ type: 'text', text: 'started subagent lead' }] } }),
      event(8, 'assistant/message', { message: { role: 'assistant', source: { provider: 'provider-a', model: 'model-a', replayState: 'private state' }, content: [{ type: 'reasoning', text: 'hidden chain' }, { type: 'text', text: 'Visible decision' }] }, stream: [{ type: 'reasoning', text: 'stream chain' }] }),
      // Unknown plugin records are preserved by DSH, but are not blindly copied into disclosure.
      event(9, 'plugin:unknown', { secret: 'skip-this-record' })
    ] },
    lead: { header: { id: 'lead', parentSession: 'captain', delegationDepth: 1, agentPreset: 'mcm-model-lead' }, events: [
      event(0, 'request/context', { provider: 'provider-b', model: 'model-b' }),
      event(1, 'user/message', message('Compare mechanisms')),
      event(2, 'assistant/message', { message: { content: [{ type: 'text', text: 'Model contract v1' }] } })
    ] },
    recovered: { header: { id: 'recovered', parentSession: 'lead', delegationDepth: 2, agentPreset: 'mcm-modeler' }, events: [
      event(0, 'user/message', { role: 'user', content: [{ type: 'text', text: 'Use uploaded image' }, { type: 'image', attachmentId: 'sha256:image1', mediaType: 'image/png', width: 100, height: 70, bytes: 300 }] }),
      event(1, 'assistant/message', { message: { source: { provider: 'provider-b', model: 'model-c' }, content: [{ type: 'text', text: 'Recovered result' }] } })
    ] }
  };
  const flushed = [];
  const opened = [];
  const closed = [];
  const deps = {
    sessions: {
      get: (id) => id === 'recovered' ? undefined : { id },
      flush: async (session) => { flushed.push(session.id); if (failFlush === session.id) throw new Error('flush failed'); }
    },
    sessionQuery: { traceSession: async () => { if (failLineage) throw new Error('lineage unavailable'); return { descendants: [local('lead', [local('recovered')])] }; } },
    sessionPersistence: { open: async (id, mode) => {
      assert.equal(mode, 'read'); opened.push(id);
      if (!records[id]) throw new Error('missing session');
      return { header: records[id].header,
        read: async (offset, length) => { assert.equal(offset, 0); assert.equal(length, undefined); if (failRead === id) throw new Error('read failed'); return { events: records[id].events }; },
        close: async () => { closed.push(id); if (failClose === id) throw new Error('close failed'); }
      };
    } }
  };
  return { deps, flushed, opened, closed, records };
}

const options = { rootSessionId: 'captain', checkpoint: 'G3', purpose: 'Validate accepted result run', now: '2026-10-24T08:00:00Z' };

test('nested local tree and a cold restored child are read through public read handles', async () => {
  const f = fixture();
  const result = await collectAudit(f.deps, options);
  assert.equal(result.report.transcripts_complete, true);
  assert.equal(result.report.archived_sessions, 3);
  assert.equal(result.report.sessions[0].role_preset, 'mcm-captain');
  assert.deepEqual(f.flushed, ['captain', 'lead']);
  assert.deepEqual(f.opened, ['captain', 'lead', 'recovered']);
  assert.deepEqual(f.closed, ['captain', 'lead', 'recovered']);
  const index = result.files['ai-use-index.jsonl'].trim().split('\n').map(JSON.parse);
  assert.equal(index[0].role_preset, 'mcm-captain');
  assert.equal(index[2].parent_session_id, 'lead');
  assert.deepEqual(index[2].actual_models, [{ provider: 'provider-b', model: 'model-c' }]);
  assert.equal(index[0].human_verification.status, 'pending');
});

test('PTC parent and nested tool calls retain their ids, purpose and source event references', async () => {
  const { files } = await collectAudit(fixture().deps, options);
  const index = JSON.parse(files['ai-use-index.jsonl'].split('\n')[0]);
  assert.deepEqual(index.tool_calls.map((call) => call.name), ['run_code', 'subagent']);
  assert.equal(index.tool_calls[1].call_id, 'ptc-1:ptc:1');
  assert.equal(index.tool_calls[1].purpose, 'Model lead');
  assert.ok(index.prompt_event_seqs.includes(7));
  assert.deepEqual(index.visible_output_event_seqs, [8]);
});

test('actual DSH 0.2.1 PTC dispatch events enter the archive and nested-use index once', async () => {
  const f = fixture();
  f.records.captain.events.push(event(10, 'tool/ptc-dispatch-start', { rootCallId: 'ptc-2', parentCallId: 'ptc-2', subCallId: 'ptc-2:ptc:1', name: 'read', arguments: { file_path: 'results/manifest.json' } }));
  f.records.captain.events.push(event(11, 'tool/ptc-dispatch', { rootCallId: 'ptc-2', parentCallId: 'ptc-2', subCallId: 'ptc-2:ptc:1', name: 'read', arguments: { file_path: 'results/manifest.json' }, content: [{ type: 'text', text: 'Verified manifest' }], isError: false }));
  const result = await collectAudit(f.deps, options);
  const index = JSON.parse(result.files['ai-use-index.jsonl'].split('\n')[0]);
  assert.equal(index.tool_calls.filter((call) => call.call_id === 'ptc-2:ptc:1').length, 1);
  const linked = index.tool_calls.find((call) => call.call_id === 'ptc-2:ptc:1');
  assert.equal(linked.root_call_id, 'ptc-2');
  assert.equal(linked.parent_call_id, 'ptc-2');
  assert.equal(linked.result_event_seq, 11);
  assert.equal(linked.state, 'completed');
  assert.deepEqual(linked.arguments, { file_path: 'results/manifest.json' });
  assert.ok(Object.values(result.files).join('\n').includes('tool/ptc-dispatch-start'));
  assert.ok(Object.values(result.files).join('\n').includes('Verified manifest'));
});

test('public native ToolDefinition schemas have standard required arrays and reject malformed inputs', async () => {
  const f = toolFixture();
  const tool = createAuditTool(f.ctx);
  assert.equal(tool.parameters.type, 'object');
  assert.deepEqual(tool.parameters.required, ['checkpoint', 'purpose']);
  assert.equal(tool.parameters.properties.checkpoint.required, undefined);
  assert.ok(Array.isArray(tool.output.schema.required));
  await assert.rejects(tool.execute({ checkpoint: 12, purpose: 'p' }, f.exec), /must be strings/);
  await assert.rejects(tool.execute({ checkpoint: 'g', purpose: 'p', unknown: true }, f.exec), /Invalid archive arguments/);
});

test('reasoning, private replay state and credential values never enter the filtered archive', async () => {
  const { files, report } = await collectAudit(fixture().deps, options);
  const all = Object.values(files).join('\n');
  for (const forbidden of ['hidden chain', 'stream chain', 'private state', 'do-not-export', 'credential-value', 'skip-this-record']) assert.equal(all.includes(forbidden), false, forbidden);
  assert.ok(all.includes('Visible decision'));
  assert.ok(all.includes('[REDACTED]'));
  assert.ok(all.includes('maxTokens'));
  assert.ok(report.filtering.removed_fields > 0);
  assert.ok(report.filtering.removed_blocks > 0);
});

test('attachment references are explicit and never falsely reported as archived bytes', async () => {
  const result = await collectAudit(fixture().deps, options);
  const manifest = JSON.parse(result.files['attachments.json']);
  assert.deepEqual(manifest.references, [{ attachmentId: 'sha256:image1', mediaType: 'image/png', bytes: 300, width: 100, height: 70, archived_bytes: false }]);
  assert.equal(result.report.attachment_bytes_included, false);
  assert.equal(result.report.human_verification_complete, false);
  assert.equal(result.report.sessions[0].exported_through_seq, 9);
});

for (const mode of ['failRead', 'failFlush', 'failClose']) test(`${mode} produces a partial archive with the affected session identified`, async () => {
  const f = fixture({ [mode]: 'lead' });
  const result = await collectAudit(f.deps, options);
  assert.equal(result.report.transcripts_complete, false);
  assert.ok(result.report.warnings.some((warning) => warning.session_id === 'lead'));
  assert.equal(result.report.archived_sessions, mode === 'failClose' ? 3 : 2);
  if (mode === 'failRead') assert.ok(f.closed.includes('lead'));
});

test('failed lineage exports the known root and does not claim complete tree coverage', async () => {
  const result = await collectAudit(fixture({ failLineage: true }).deps, options);
  assert.equal(result.report.transcripts_complete, false);
  assert.equal(result.report.archived_sessions, 1);
  assert.equal(result.report.warnings[0].code, 'lineage_unavailable');
});

test('cancellation propagates rather than being converted to a successful partial export', async () => {
  const controller = new AbortController(); controller.abort(new Error('cancelled'));
  await assert.rejects(collectAudit(fixture().deps, { ...options, signal: controller.signal }), /cancelled/);
});

test('visible scientific analysis survives and common credential spellings are filtered', () => {
  assert.deepEqual(visibleValue({ analysis: 'sensitivity analysis', apiKey: 'x', accessToken: 'y', clientSecret: 'z', content: [{ type: 'thinking', text: 'hidden' }] }), { analysis: 'sensitivity analysis', content: [] });
  assert.deepEqual(visibleValue([{ type: 'reasoning-signature', text: 'private' }, { type: 'text', text: 'result' }]), [{ type: 'text', text: 'result' }]);
  assert.equal(redactText('Bearer secret123 api_key="abc" ghp_abcdefghijklmnop'), 'Bearer [REDACTED] api_key=[REDACTED] [REDACTED]');
  assert.deepEqual(visibleValue({ DEEPSEEK_API_KEY: 'credential', max_tokens: 300 }), { max_tokens: 300 });
  assert.equal(redactText('DEEPSEEK_API_KEY=abc https://user:pass@example.test'), 'DEEPSEEK_API_KEY=[REDACTED] https://[REDACTED]@example.test');
});

function toolFixture({ role = 'mcm-captain', marker = true, sandbox = true } = {}) {
  const f = fixture();
  const root = resolve('project-fixture');
  const writes = [];
  const policy = { mode: 'workspace-write', workspaceRoot: root };
  const ctx = { ...f.deps,
    sessionProjections: { stateOf: () => role },
    workingDirectory: { ensure: async () => root },
    get: (key) => key === 'sandboxPolicy' && sandbox ? { resolve: () => policy } : undefined,
    fs: {
      sandboxMode: 'workspace-write',
      resolve: async (path) => ({ targetKey: resolve(path), displayPath: resolve(path) }),
      stat: async () => marker ? { type: 'directory' } : undefined,
      writeText: async (target, text, guard, signal, suppliedPolicy) => {
        assert.equal(guard.kind, 'createIfAbsent'); assert.equal(suppliedPolicy, policy);
        assert.ok(target.targetKey.startsWith(root)); writes.push({ target, text });
      }
    }
  };
  const exec = { agent: { session: { id: 'captain', header: { cwd: root, agentPreset: 'standard' } } }, signal: new AbortController().signal };
  return { ctx, exec, writes, root };
}

test('tool adapter honors current selected role, initial root and standing sandbox on every new file', async () => {
  const f = toolFixture();
  const result = await createAuditTool(f.ctx).execute({ checkpoint: '../../final', purpose: 'Final gate' }, f.exec);
  assert.ok(result.directory.startsWith(resolve(f.root, 'logs', 'ai-audit')));
  assert.equal(result.transcripts_complete, true);
  assert.equal(f.writes.length, 6);
  assert.equal(result.human_verification_complete, false);
});

test('tool adapter rejects another project root, absent marker, non-captain and missing sandbox policy', async () => {
  const f = toolFixture();
  await assert.rejects(createAuditTool(f.ctx).execute({ checkpoint: 'g', purpose: 'p', project_root: resolve('another-project') }, f.exec), /initial directory/);
  for (const [settings, expected] of [[{ marker: false }, /marker/], [{ role: 'mcm-modeler' }, /restricted/], [{ sandbox: false }, /sandboxPolicy/]]) {
    const x = toolFixture(settings);
    await assert.rejects(createAuditTool(x.ctx).execute({ checkpoint: 'g', purpose: 'p' }, x.exec), expected);
    assert.equal(x.writes.length, 0);
  }
});

test('an archive write failure rejects the tool and never reports a complete saved archive', async () => {
  const f = toolFixture();
  let attempts = 0;
  f.ctx.fs.writeText = async () => { attempts++; throw new Error('FS_SANDBOX_DENIED: read-only session'); };
  await assert.rejects(createAuditTool(f.ctx).execute({ checkpoint: 'final', purpose: 'Final review' }, f.exec), /FS_SANDBOX_DENIED/);
  assert.equal(attempts, 1);
});
