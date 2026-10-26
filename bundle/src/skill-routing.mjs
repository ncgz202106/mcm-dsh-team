/** Task routing metadata, not an SDK permission boundary or proof of installed capabilities. */
export const EXCLUDED_ORCHESTRATORS = [
  'shumo2', 'shumo2-v2', 'shumo-core', 'askill', 'askill-v2',
  'math-modeling', 'mathematical-modeling', 'paper-spine'
];

export const OPTIONAL_ROLES = {
  'mcm-code-lead': {
    enabled_by_default: false,
    requires_explicit_enable: true,
    allowed_parent: 'mcm-captain',
    allowed_children: ['mcm-programmer'],
    reason: 'Only enable for real parallel implementation and integration work after capacity and host capabilities are checked.'
  }
};

const route = (task_type, primary_skill, optional_skills, branch, limits) =>
  ({ task_type, primary_skill, optional_skills, branch, limits });

export const SKILL_ROUTING = {
  format_version: 1,
  bundle_version: '0.2.0',
  routing_is_behavioral: true,
  defaults: {
    max_primary_skills_per_task: 1,
    preload_all_skills: false,
    require_actual_discovery_and_read: true,
    require_dependency_preflight: true,
    project_backend_first: true,
    skill_may_spawn_without_parent_approval: false,
    skill_may_resume_paused_work: false,
    excluded_orchestrators_apply_to_indirect_routes: true
  },
  excluded_orchestrators: EXCLUDED_ORCHESTRATORS,
  restricted_skills: {
    'nature-citation': 'Only when the user explicitly requests Nature/CNS-only source scope; never the default MCM literature search.',
    'nature-data': 'Only for explicitly assigned Data/Code Availability or repository planning, not data cleaning; publication requires its own authorization.',
    'venue-templates': 'Do not replace the established MCM template with a journal template.'
  },
  roles: {
    'mcm-captain': [],
    'mcm-model-lead': [route('statistical-design-audit', 'nature-statistics', [], 'relevant statistical design only', 'No new model or experiment without a scoped contract; ordinary modeling tasks need no forced skill.')],
    'mcm-modeler': [route('statistical-assumption-audit', 'nature-statistics', [], 'relevant statistical assumptions only', 'Preserve the blind phase and declared scope; do not import a full modeling orchestrator.')],
    'mcm-evidence': [
      route('literature-gap-search', 'nature-academic-search', ['nature-downloader', 'nature-ref-verifier'], 'multi-source-search', 'Use unrestricted subject-appropriate sources; no automatic citation-impact or timed literature pipeline.'),
      route('citation-field-verification', 'nature-ref-verifier', [], 'verify supplied references', 'Correct DOI/metadata does not prove that the source supports the manuscript claim.'),
      route('lawful-fulltext-retrieval', 'nature-downloader', [], 'OA/publisher/user-authorized access', 'Report actual reading scope; never invent full-text access.')
    ],
    'mcm-programmer': [route('statistical-output-audit', 'nature-statistics', [], 'only assigned statistics with data', 'Ordinary code solving uses the approved formula/code contract; independent verification remains outside the author branch.')],
    'mcm-code-lead': [],
    'mcm-verifier': [
      route('statistical-validity-review', 'nature-statistics', [], 'units, independence, uncertainty and test validity', 'No new analysis without explicit data/task; distinguish reproduction from scientific validity.'),
      route('citation-audit', 'nature-ref-verifier', [], 'selected claim/reference checks', 'Review original support as well as bibliographic fields.')
    ],
    'mcm-paper-lead': [
      route('argument-and-section-integration', 'nature-writing', ['nature-polishing'], 'generic, English, assigned MCM sections', 'Keep the user seven-part framework and MCM rules; no Nature submission package or replacement outline.'),
      route('language-compression', 'nature-polishing', [], 'language and organization only', 'Preserve numbers, symbols, citations and conclusion strength; scientific changes return upstream.')
    ],
    'mcm-writer': [
      route('section-draft', 'nature-writing', ['nature-polishing'], 'generic, English, assigned subsection', 'Write only task-owned drafts under the user framework; do not edit the integrated manuscript.'),
      route('language-edit', 'nature-polishing', [], 'language-only editing', 'Do not strengthen evidence or change model/results.')
    ],
    'mcm-figure': [
      route('quantitative-figure', 'nature-figure', ['nature-statistics'], 'project-selected Python/R scientific figures', 'Fixed result inputs and figure contract; final-size 12pt core labels; new estimators/tests/filters return upstream.'),
      route('method-or-geometry-diagram', 'fireworks-tech-graph', [], 'editable SVG technical diagram', 'Default 1–2 framework/method schematics for the whole paper; no invented measurements or generative result plots.')
    ],
    'mcm-typesetter': [route('pdf-layout-review', 'pdf', [], 'render and inspect pages', 'Compile through the verified project LaTeX entry; pdf is not a complete TeX compiler or a scientific validator.')],
    'mcm-reviewer': [route('independent-manuscript-review', 'nature-reviewer', ['nature-statistics', 'nature-ref-verifier', 'pdf'], 'evidence-grounded critique only', 'Score by MCM problem/rules and internal rubric, not Nature novelty or editorial acceptance criteria.')]
  }
};

export function validateSkillRouting(roleIds) {
  if (new Set(roleIds).size !== roleIds.length) throw new Error('Duplicate role ID');
  const actual = Object.keys(SKILL_ROUTING.roles).sort();
  if (JSON.stringify(actual) !== JSON.stringify([...roleIds].sort())) throw new Error('Skill routes must cover exactly the preset role IDs');
  for (const [role, routes] of Object.entries(SKILL_ROUTING.roles)) {
    const tasks = new Set();
    for (const entry of routes) {
      if (!entry.task_type || tasks.has(entry.task_type)) throw new Error(`${role}: duplicate or missing task route`);
      tasks.add(entry.task_type);
      if (!entry.primary_skill || !Array.isArray(entry.optional_skills)) throw new Error(`${role}: incomplete skill route`);
      for (const skill of [entry.primary_skill, ...entry.optional_skills]) {
        if (EXCLUDED_ORCHESTRATORS.includes(skill) || skill in SKILL_ROUTING.restricted_skills) throw new Error(`${role}: restricted automatic route ${skill}`);
      }
    }
  }
  return true;
}

export function renderSkillRouting(roleId) {
  const routes = SKILL_ROUTING.roles[roleId];
  if (!routes) throw new Error(`Unknown skill-routing role: ${roleId}`);
  const lines = routes.length
    ? routes.map((entry) => `- ${entry.task_type} → ${entry.primary_skill}；分支：${entry.branch}；按需辅助：${entry.optional_skills.join(', ') || '无'}。边界：${entry.limits}`)
    : ['- 本角色没有强制默认专项 Skill；按任务具体缺口选择，不能为了调用而增加流程。'];
  return [
    '## 本角色专项 Skill 路由（构建器内嵌）',
    ...lines,
    '任务先选一个主 Skill，按需读取匹配 SKILL.md 及必要分支，核实实际工具/依赖；发现、读取、执行成功分别留证。以上名称不是已运行证明，缺技能/工具报告父层。',
    `本项目不自动启动全流程总控：${EXCLUDED_ORCHESTRATORS.join('、')}。nature-citation、nature-data、venue-templates 限于明确专项授权，不能取代当前任务与MCM框架。`,
    '被排除总控也不得由专项 Skill 间接唤起；读取必要引用时核对引用链，跳过冲突启动步骤并向父层报告。',
    'Skill 不增加派生、写入、发布或恢复权限；需要子 Agent 的叶子角色向父层请求分包；保留项目后端、用户约束、证据和非作者验收。'
  ].join('\n');
}
