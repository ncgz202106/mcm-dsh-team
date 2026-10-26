import { createHash } from 'node:crypto';

const HIDDEN_TYPES = new Set(['reasoning', 'thinking', 'analysis', 'redacted_thinking', 'reasoning_content', 'private']);
const HIDDEN_KEYS = /^(?:reasoning(?:_content)?|thinking|stream|replayState|private(?:_.+)?|internal(?:_.+)?|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|token|authorization|credentials?|password|passphrase|secret|cookie|set-cookie)$/i;
const ENV_SECRET_KEY = /(?:^|[_-])(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|secret)$/i;
const ALLOWED_EVENTS = new Set(['request/context', 'request/header', 'system/message', 'developer/message', 'user/message', 'assistant/message', 'tool/call', 'tool/result', 'tool/ptc-dispatch-start', 'tool/ptc-dispatch', 'turn/start', 'turn/end', 'step/start', 'step/end', 'subagent/catalog', 'agent-preset/selected']);

export function redactText(text) {
  return String(text)
    .replace(/\bBearer\s+[A-Za-z0-9._~+\/-]+/gi, 'Bearer [REDACTED]')
    .replace(/\b(?:sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,})\b/g, '[REDACTED]')
    .replace(/\b((?:[A-Za-z0-9]+_)*(?:api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|password|secret))\s*[:=]\s*(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;\r\n]+)/gi, '$1=[REDACTED]')
    .replace(/(https?:\/\/)[^\s/@:]+:[^\s/@]+@/gi, '$1[REDACTED]@');
}

/** Preserve visible JSON facts only. Never copy provider streams, reasoning or credential fields. */
export function visibleValue(value, stats = { removed_fields: 0, removed_blocks: 0 }) {
  if (typeof value === 'string') return redactText(value);
  if (value === null || typeof value !== 'object') return value;
  const blockType = String(value.type ?? '').toLowerCase();
  if (HIDDEN_TYPES.has(blockType) || /^(?:reasoning|thinking|analysis|private|internal)(?:[_/-]|$)|^redacted[_-](?:reasoning|thinking)/.test(blockType)) { stats.removed_blocks++; return undefined; }
  if (Array.isArray(value)) return value.map((item) => visibleValue(item, stats)).filter((item) => item !== undefined);
  const out = {};
  for (const [key, item] of Object.entries(value)) {
    if (HIDDEN_KEYS.test(key) || ENV_SECRET_KEY.test(key)) { stats.removed_fields++; continue; }
    const clean = visibleValue(item, stats);
    if (clean !== undefined) out[key] = clean;
  }
  return out;
}

export function projectEvent(event, stats) {
  if (!ALLOWED_EVENTS.has(event.type)) return undefined;
  const result = { seq: event.seq, type: event.type, ...(event.time === undefined ? {} : { time: event.time }), data: visibleValue(event.data, stats) };
  if (event.surfaceOp !== undefined) result.surfaceOp = visibleValue(event.surfaceOp, stats);
  if (event.sourceEventSeqs !== undefined) result.sourceEventSeqs = event.sourceEventSeqs;
  return result;
}

export function collectAttachments(value, refs = new Map()) {
  if (!value || typeof value !== 'object') return refs;
  if (!Array.isArray(value) && typeof value.attachmentId === 'string') {
    const reference = {};
    for (const key of ['attachmentId', 'mediaType', 'name', 'bytes', 'width', 'height']) if (value[key] !== undefined) reference[key] = visibleValue(value[key]);
    refs.set(value.attachmentId, { ...refs.get(value.attachmentId), ...reference, archived_bytes: false });
  }
  for (const item of Object.values(value)) if (item && typeof item === 'object') collectAttachments(item, refs);
  return refs;
}

const safeError = (error) => redactText(error instanceof Error ? error.message : String(error));
const fileId = (id) => `${String(id).replace(/[^A-Za-z0-9_-]/g, '_').slice(0, 48)}-${createHash('sha256').update(String(id)).digest('hex').slice(0, 10)}`;

function sessionIndex(header, events, checkpoint, purpose) {
  const models = new Map();
  const tools = [];
  const calls = new Map();
  const prompts = [];
  const outputs = [];
  let role = header.agentPreset ?? null;
  for (const event of events) {
    const data = event.data ?? {};
    if (event.type === 'agent-preset/selected' && typeof data.agentPreset === 'string') role = data.agentPreset;
    const source = data.message?.source;
    const route = event.type === 'request/context' ? data : source;
    if (route?.provider && route?.model) models.set(`${route.provider}\0${route.model}`, { provider: route.provider, model: route.model });
    if (['system/message', 'developer/message', 'user/message', 'tool/result'].includes(event.type)) prompts.push(event.seq);
    if (event.type === 'assistant/message') outputs.push(event.seq);
    if (event.type === 'tool/call' || event.type === 'tool/ptc-dispatch-start') {
      const id = data.callId ?? data.subCallId ?? null;
      const call = { seq: event.seq, call_id: id, root_call_id: data.rootCallId ?? id,
        parent_call_id: data.parentCallId ?? null, name: data.name ?? null,
        arguments: data.arguments ?? null, purpose: data.arguments?.description ?? data.arguments?.purpose ?? null,
        result_event_seq: null, state: 'started' };
      tools.push(call);
      if (id !== null) calls.set(id, call);
    }
    if (event.type === 'tool/result' || event.type === 'tool/ptc-dispatch') {
      const id = data.subCallId ?? data.message?.callId ?? null;
      let call = calls.get(id);
      if (!call && event.type === 'tool/ptc-dispatch') {
        call = { seq: null, call_id: id, root_call_id: data.rootCallId ?? null, parent_call_id: data.parentCallId ?? null,
          name: data.name ?? null, arguments: data.arguments ?? null,
          purpose: data.arguments?.description ?? data.arguments?.purpose ?? null, result_event_seq: null, state: 'started', start_event_missing: true };
        tools.push(call); calls.set(id, call);
      }
      if (call) { call.result_event_seq = event.seq; call.state = (data.isError ?? data.message?.isError) === true ? 'failed' : 'completed'; }
    }
  }
  return {
    session_id: header.id, parent_session_id: header.parentSession ?? null, role_preset: role,
    checkpoint, checkpoint_purpose: purpose, actual_models: [...models.values()],
    prompt_event_seqs: prompts, visible_output_event_seqs: outputs, tool_calls: tools,
    human_verification: { status: 'pending', reviewer: null, checked_at: null, evidence: [] }
  };
}

/**
 * Read-only public DSH interfaces, identical to the native export's read path.
 * Produces a filtered evidence snapshot, not a replayable canonical Session export.
 */
export async function collectAudit(deps, { rootSessionId, checkpoint, purpose, signal, now = new Date().toISOString() }) {
  if (!rootSessionId || !checkpoint?.trim() || !purpose?.trim()) throw new Error('rootSessionId, checkpoint and purpose are required');
  checkpoint = redactText(checkpoint);
  purpose = redactText(purpose);
  const warnings = [];
  const ids = [rootSessionId];
  const seen = new Set(ids);
  try {
    const lineage = await deps.sessionQuery.traceSession(rootSessionId, signal);
    const visit = (nodes) => {
      for (const node of nodes ?? []) {
        const id = node.session?.header?.id;
        if (!id) { warnings.push({ code: 'unreadable_lineage_node', message: 'A descendant has no readable local session header.' }); continue; }
        if (seen.has(id)) continue;
        seen.add(id); ids.push(id); visit(node.descendants);
      }
    };
    visit(lineage.descendants);
  } catch (error) { warnings.push({ code: 'lineage_unavailable', message: safeError(error) }); }
  const files = {};
  const sessions = [];
  const indexes = [];
  const attachments = new Map();
  const stats = { removed_fields: 0, removed_blocks: 0 };
  for (const id of ids) {
    signal?.throwIfAborted();
    let handle;
    try {
      const live = deps.sessions.get(id);
      if (live) await deps.sessions.flush(live);
      handle = await deps.sessionPersistence.open(id, 'read', signal ? { signal } : {});
      const { events } = await handle.read(0, undefined, signal ? { signal } : {});
      if (!Array.isArray(events)) throw new Error('Persistence returned no event array');
      const visible = events.map((event) => projectEvent(event, stats)).filter(Boolean);
      const header = visibleValue(handle.header, stats);
      const path = `sessions/${fileId(id)}.visible.jsonl`;
      files[path] = `${[JSON.stringify({ type: 'mcm-visible-session', schema_version: 1, header }), ...visible.map((event) => JSON.stringify(event))].join('\n')}\n`;
      const index = sessionIndex(header, visible, checkpoint, purpose);
      sessions.push({ session_id: id, role_preset: index.role_preset, path, source_event_count: events.length,
        visible_event_count: visible.length, exported_through_seq: events.at(-1)?.seq ?? null,
        sha256: createHash('sha256').update(files[path]).digest('hex') });
      indexes.push(index);
      for (const event of visible) collectAttachments(event, attachments);
      if (header.origin?.kind === 'external') warnings.push({ code: 'external_session_unsupported', session_id: id, message: 'External backend internal conversations are outside v1 coverage.' });
    } catch (error) {
      signal?.throwIfAborted();
      warnings.push({ code: 'session_read_failed', session_id: id, message: safeError(error) });
    } finally {
      if (handle) try { await handle.close(); } catch (error) { warnings.push({ code: 'session_close_failed', session_id: id, message: safeError(error) }); }
    }
  }
  const report = {
    schema_version: 1, root_session_id: rootSessionId, checkpoint, purpose, captured_at: now,
    transcripts_complete: warnings.length === 0 && sessions.length === ids.length,
    discovered_sessions: ids.length, archived_sessions: sessions.length, sessions, warnings, filtering: stats,
    attachment_count: attachments.size, attachment_bytes_included: false, human_verification_complete: false,
    limitations: [
      'Filtered visible evidence snapshot; not a replayable original DSH Session log.',
      'Each session has its own recorded cutoff; future messages and this archive tool result are outside that cutoff.',
      'Attachments are references only. Preserve original project inputs or the native /export ZIP with attachments.',
      'Credentials are filtered by field names and common textual patterns; inspect the archive before sharing.',
      'No hidden reasoning is collected. Human verification remains pending until a human records actual checks.',
      'Only local spawn session trees are covered; external backend internal messages are not captured.'
    ]
  };
  files['manifest.json'] = `${JSON.stringify(report, null, 2)}\n`;
  files['attachments.json'] = `${JSON.stringify({ schema_version: 1, archived_bytes: false, references: [...attachments.values()] }, null, 2)}\n`;
  files['ai-use-index.jsonl'] = `${indexes.map((index) => JSON.stringify(index)).join('\n')}${indexes.length ? '\n' : ''}`;
  return { report, files };
}
