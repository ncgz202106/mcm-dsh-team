import { nativePlanning } from './native-plan.mjs';
import { OPTIONAL_ROLES, validateSkillRouting } from './skill-routing.mjs';

/** Role definitions use the actual installed DSH 0.2.1-rc.2 preset API. */
export const ROLES = [
  { id: 'mcm-captain', name: '美赛 · 队长', description: 'MCM A/B/C sole internal dispatcher; optional Codex checkpoint director, evidence gates and delivery.', children: ['mcm-model-lead', 'mcm-evidence', 'mcm-programmer', 'mcm-code-lead', 'mcm-verifier', 'mcm-paper-lead', 'mcm-reviewer'] },
  { id: 'mcm-model-lead', name: '美赛 · 主建模手', description: 'Own the model specification and coordinate two or more independent modelers.', children: ['mcm-modeler'] },
  { id: 'mcm-modeler', name: '美赛 · 专项建模手', description: 'Independently interpret the problem and develop, compare and challenge candidate models.' },
  { id: 'mcm-evidence', name: '美赛 · 文献与数据检索', description: 'Verify literature, parameters and datasets; deliver traceable evidence and data audits.' },
  { id: 'mcm-programmer', name: '美赛 · 编程手', description: 'Reusable solver/experiment instances under captain or optional code lead; reproducible results.' },
  { id: 'mcm-code-lead', name: '美赛 · 编程统筹（可选）', description: 'Optional, off by default: integrate parallel programmers within an explicitly granted subtree budget.', children: ['mcm-programmer'], optional: true },
  { id: 'mcm-verifier', name: '美赛 · 独立验证手', description: 'Independently test equations, code, leakage, dimensions and numerical results.' },
  { id: 'mcm-paper-lead', name: '美赛 · 论文统筹', description: 'Own the paper, claim alignment, LaTeX integration, PDF review and submission requirements.', children: ['mcm-writer', 'mcm-figure', 'mcm-typesetter'] },
  { id: 'mcm-writer', name: '美赛 · 论文写作', description: 'Write evidence-grounded English sections and the Summary Sheet using accepted results.' },
  { id: 'mcm-figure', name: '美赛 · 图表设计', description: 'Build reproducible data figures, captions and source manifests from accepted runs.' },
  { id: 'mcm-typesetter', name: '美赛 · LaTeX与排版', description: 'Integrate LaTeX, compile PDF, inspect rendered pages and maintain a portable source package.' },
  { id: 'mcm-reviewer', name: '美赛 · 审阅老师', description: 'Independently assess modeling, evidence, reproducibility and communication; route findings to the captain.' }
];
validateSkillRouting(ROLES.map((role) => role.id));
export { OPTIONAL_ROLES };

const row = (id, name, config, extra = {}) => ({ id, name, ...(config === undefined ? {} : { config }), ...extra });
export const rawYaml = (source) => ({ __rawYaml: source });

/** Complete per-role tool lists, derived from the installed PTC preset, not old directory presets. */
export function rolePlugins(role, prefix) {
  const plugins = [
    row('persona', '@deepseek-ai/dsh-persona', { prefix, complete: false, includeRuntimeContext: true }),
    row('agent-instructions', '@deepseek-ai/dsh-agent-instructions', { maxBytes: 65536, projectRootMarkers: ['.mcm-project', '.git'] }),
    row('time-context', '@deepseek-ai/dsh-time-context'),
    row('tool-bash', '@deepseek-ai/dsh-tool-bash', undefined, { disabled: rawYaml("!!js process.platform === 'win32'") }),
    row('tool-pwsh', '@deepseek-ai/dsh-tool-pwsh', undefined, { disabled: rawYaml("!!js process.platform !== 'win32'") }),
    row('tool-fs', '@deepseek-ai/dsh-tool-fs'),
    row('tool-fs-search', '@deepseek-ai/dsh-tool-fs-search', { sampleOverCapGlobResults: false }),
    row('tool-jobs', '@deepseek-ai/dsh-tool-jobs'),
    row('skill-filesystem', '@deepseek-ai/dsh-skill-filesystem', { watch: false }),
    row('tool-skill', '@deepseek-ai/dsh-tool-skill'),
    ...(role.id === 'mcm-captain' ? [structuredClone(nativePlanning)] : []),
    {
      id: 'compaction', name: 'cordis:group', group: true,
      isolate: { compaction: true, toolResultPruner: true },
      config: [
        row('compaction-basic', '@deepseek-ai/dsh-compaction-basic'),
        row('command-compact', '@deepseek-ai/dsh-command-compact'),
        row('tool-result-pruner', '@deepseek-ai/dsh-compaction-tool-result-pruner', { thresholdChars: 8192, headChars: 4096, tailChars: 1024 })
      ]
    },
    // Leaf roles retain the same parent-child return channel, without a delegation tool.
    row('tool-subagent-control', '@deepseek-ai/dsh-tool-subagent-control')
  ];
  if (role.children?.length) {
    plugins.push(row('tool-subagent-list-agents', '@deepseek-ai/dsh-tool-subagent-control/list-agents'));
    plugins.push(row('tool-subagent', '@deepseek-ai/dsh-tool-subagent', {
      provider: 'spawn', toolName: 'subagent', modelSelectionSettings: true,
      allowedAgentPresets: role.children, maxDepth: 2
    }));
  }
  if (role.id === 'mcm-captain') plugins.push(row('tool-ask-user', '@deepseek-ai/dsh-tool-ask-user'));
  plugins.push(
    row('tool-todo', '@deepseek-ai/dsh-tool-todo', { allowParallelInProgress: true }),
    row('tool-web', '@deepseek-ai/dsh-tool-web', { fetch: true, searchTimeoutMs: 60000 }),
    row('tool-presentation', '@deepseek-ai/dsh-agent-tool-presentation', { mode: 'ptc' }),
    row('present', '@deepseek-ai/dsh-tool-present')
  );
  if (role.id === 'mcm-captain') plugins.push(row('mcm-audit', 'dsh-mcm-team/src/archive-plugin.mjs'));
  plugins.push(row('mcm-runtime-guard', 'dsh-mcm-team/src/runtime-guard-plugin.mjs', { role: role.id }));
  return plugins;
}

export function presetDeclarations(prompts) {
  return [{ insert: ROLES.map((role, index) => ({
    id: `preset-${role.id}`, name: '@deepseek-ai/dsh-agent-preset',
    config: { id: role.id, name: role.name, description: role.description, order: 200 + index,
      plugins: rolePlugins(role, prompts[role.id]) }
  })) }];
}

/** Tiny deterministic emitter for our fixed entry-list schema; raw expressions are internal constants only. */
export function emitYaml(value, indent = 0) {
  const pad = ' '.repeat(indent);
  const scalar = (v) => v && typeof v === 'object' && Object.keys(v).length === 1 && '__rawYaml' in v
    ? v.__rawYaml : JSON.stringify(v);
  if (Array.isArray(value)) return value.length === 0 ? `${pad}[]` : value.map((item) => {
    if (item === null || typeof item !== 'object' || '__rawYaml' in item) return `${pad}- ${scalar(item)}`;
    const rendered = emitYaml(item, indent + 2).split('\n');
    return `${pad}- ${rendered[0].slice(indent + 2)}${rendered.length > 1 ? '\n' + rendered.slice(1).join('\n') : ''}`;
  }).join('\n');
  return Object.entries(value).map(([key, v]) => {
    if (v && typeof v === 'object' && !('__rawYaml' in v) && (Array.isArray(v) ? v.length > 0 : Object.keys(v).length > 0)) {
      return `${pad}${key}:\n${emitYaml(v, indent + 2)}`;
    }
    if (typeof v === 'string' && v.includes('\n')) return `${pad}${key}: |-\n${v.split('\n').map((line) => line.trim() ? `${' '.repeat(indent + 2)}${line}` : '').join('\n')}`;
    return `${pad}${key}: ${scalar(v)}`;
  }).join('\n');
}
