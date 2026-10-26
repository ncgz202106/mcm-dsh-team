import { createAuditTool } from './archive-tool.mjs';

export const name = 'mcm-audit';
export const inject = ['tools', 'sessions', 'sessionQuery', 'sessionPersistence', 'sessionProjections', 'fs', 'workingDirectory'];

export function apply(ctx) {
  ctx.tools.register(createAuditTool(ctx));
}
