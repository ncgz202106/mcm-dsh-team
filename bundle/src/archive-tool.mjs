import { resolve, join, isAbsolute } from 'node:path';
import { randomUUID } from 'node:crypto';
import { collectAudit } from './archive-core.mjs';

/** Convert our fixed parameter-spec literals to the public ToolDefinition JSON Schema. */
function schemaNode(node) {
  const output = {};
  for (const [key, value] of Object.entries(node)) if (key !== 'required' && key !== 'properties') output[key] = value;
  if (node.properties) {
    output.properties = Object.fromEntries(Object.entries(node.properties).map(([key, value]) => [key, schemaNode(value)]));
    output.required = Object.entries(node.properties).filter(([, value]) => value.required === true).map(([key]) => key);
  }
  return output;
}

function nativeDefinition(spec) {
  return { ...spec,
    parameters: schemaNode({ type: 'object', additionalProperties: false, properties: spec.parameters }),
    output: { ...spec.output, schema: schemaNode(spec.output.schema) }
  };
}

/** Scoped captain tool. Reads native logs and writes only fresh files beneath the initial project root. */
export function createAuditTool(ctx) {
  return nativeDefinition({
    name: 'mcm_archive_audit',
    description: 'Archive a filtered snapshot of this MCM captain and all local spawn descendants using DSH public read handles. Writes fresh files under logs/ai-audit in the original project directory. Reports partial reads and exact cutoffs; attachment bytes and human verification require a separate final check. Does not collect reasoning or change Session logs.',
    parameters: {
      checkpoint: { type: 'string', required: true, description: 'Stable checkpoint label such as G1-model, G3-results or final.' },
      purpose: { type: 'string', required: true, description: 'Why this evidence snapshot is being taken and which task/gate it supports.' },
      project_root: { type: 'string', description: 'Optional original project root; must equal this captain Session initial directory.' }
    },
    output: {
      schema: { type: 'object', additionalProperties: false, properties: {
        directory: { type: 'string', required: true },
        transcripts_complete: { type: 'boolean', required: true },
        archived_sessions: { type: 'integer', required: true },
        discovered_sessions: { type: 'integer', required: true },
        warnings: { type: 'integer', required: true },
        attachment_count: { type: 'integer', required: true },
        human_verification_complete: { type: 'boolean', required: true }
      } },
      render: (_args, value) => [{ type: 'text', text: `MCM visible-evidence snapshot: ${value.directory}\nTranscripts ${value.transcripts_complete ? 'complete at recorded cutoffs' : 'PARTIAL'} (${value.archived_sessions}/${value.discovered_sessions}); warnings=${value.warnings}. Attachments: manifest only (${value.attachment_count}); human verification: pending.` }]
    },
    async execute(args, exec) {
      if (!args || typeof args !== 'object' || Array.isArray(args) || Object.keys(args).some((key) => !['checkpoint', 'purpose', 'project_root'].includes(key))) throw new Error('Invalid archive arguments');
      if (typeof args.checkpoint !== 'string' || typeof args.purpose !== 'string' || (args.project_root !== undefined && typeof args.project_root !== 'string')) throw new Error('checkpoint, purpose and optional project_root must be strings');
      if (!exec.agent) throw new Error('mcm_archive_audit requires an owning captain Session');
      const session = exec.agent.session;
      if (ctx.sessionProjections.stateOf(session, 'agentPreset') !== 'mcm-captain') throw new Error('mcm_archive_audit is restricted to the mcm-captain preset');
      if (!args.checkpoint?.trim() || !args.purpose?.trim()) throw new Error('checkpoint and purpose must be non-empty');
      const initial = session.header.cwd;
      if (!initial || !isAbsolute(initial)) throw new Error('Captain Session has no absolute initial project directory');
      const cwd = await ctx.workingDirectory.ensure(exec.agent, exec.signal);
      const root = resolve(args.project_root ?? initial);
      const initialTarget = await ctx.fs.resolve(initial, { cwd, signal: exec.signal });
      const rootTarget = await ctx.fs.resolve(root, { cwd, signal: exec.signal });
      if (rootTarget.targetKey !== initialTarget.targetKey) throw new Error('project_root must equal the captain Session initial directory');
      const marker = await ctx.fs.resolve(join(root, '.mcm-project'), { cwd, signal: exec.signal });
      if ((await ctx.fs.stat(marker, exec.signal))?.type !== 'directory') throw new Error('Project root must contain the .mcm-project directory marker');
      const policyService = ctx.get('sandboxPolicy');
      if (ctx.fs.sandboxMode !== undefined && !policyService) throw new Error('Confining filesystem requires sandboxPolicy; refusing archive writes');
      const policy = policyService?.resolve({ session });
      const now = new Date().toISOString();
      const label = args.checkpoint.trim().replace(/[^A-Za-z0-9_-]/g, '-').slice(0, 64) || 'checkpoint';
      const directory = join(root, 'logs', 'ai-audit', `${label}-${now.replace(/[:.]/g, '-')}-${randomUUID().slice(0, 8)}`);
      const { report, files } = await collectAudit({ sessions: ctx.sessions, sessionQuery: ctx.sessionQuery, sessionPersistence: ctx.sessionPersistence }, {
        rootSessionId: session.id, checkpoint: args.checkpoint.trim(), purpose: args.purpose.trim(), signal: exec.signal, now
      });
      // Existing fs backends create parent directories and atomically publish UTF-8 files.
      // createIfAbsent prevents a repeated/overlapping export from replacing earlier evidence.
      for (const [relativePath, content] of Object.entries(files)) {
        exec.signal.throwIfAborted();
        const target = await ctx.fs.resolve(join(directory, relativePath), { cwd, signal: exec.signal });
        await ctx.fs.writeText(target, content, { kind: 'createIfAbsent' }, exec.signal, policy);
      }
      return { directory, transcripts_complete: report.transcripts_complete, archived_sessions: report.archived_sessions,
        discovered_sessions: report.discovered_sessions, warnings: report.warnings.length,
        attachment_count: report.attachment_count, human_verification_complete: false };
    }
  });
}
