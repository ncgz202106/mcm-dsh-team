import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { ROLES, presetDeclarations } from '../src/presets.mjs';
import { SKILL_ROUTING, OPTIONAL_ROLES, EXCLUDED_ORCHESTRATORS, validateSkillRouting, renderSkillRouting } from '../src/skill-routing.mjs';

const promptsRoot = new URL('../prompts/', import.meta.url);

test('JSON-exportable task routes exclude full orchestrators and restricted journal workflows', () => {
  assert.equal(validateSkillRouting(ROLES.map((role) => role.id)), true);
  const payload = JSON.parse(JSON.stringify(SKILL_ROUTING));
  assert.equal(payload.defaults.max_primary_skills_per_task, 1);
  assert.equal(payload.defaults.preload_all_skills, false);
  assert.equal(payload.defaults.skill_may_resume_paused_work, false);
  assert.equal(payload.defaults.excluded_orchestrators_apply_to_indirect_routes, true);
  for (const routes of Object.values(payload.roles)) {
    for (const route of routes) {
      assert.equal(typeof route.primary_skill, 'string');
      for (const skill of [route.primary_skill, ...route.optional_skills]) {
        assert.ok(!EXCLUDED_ORCHESTRATORS.includes(skill));
        assert.ok(!(skill in payload.restricted_skills));
      }
    }
  }
  assert.throws(() => validateSkillRouting(['mcm-captain']), /exactly/);
  assert.throws(() => validateSkillRouting(['mcm-captain','mcm-captain']), /Duplicate/);
  assert.throws(() => renderSkillRouting('invented-role'), /Unknown/);
});

test('figure, evidence, writing and review receive distinct relevant task routes', () => {
  const lookup = (role, task) => SKILL_ROUTING.roles[role].find((route) => route.task_type === task);
  assert.equal(lookup('mcm-figure', 'quantitative-figure').primary_skill, 'nature-figure');
  assert.equal(lookup('mcm-figure', 'method-or-geometry-diagram').primary_skill, 'fireworks-tech-graph');
  assert.equal(lookup('mcm-evidence', 'literature-gap-search').branch, 'multi-source-search');
  assert.equal(lookup('mcm-writer', 'section-draft').primary_skill, 'nature-writing');
  assert.equal(lookup('mcm-reviewer', 'independent-manuscript-review').primary_skill, 'nature-reviewer');
  assert.match(renderSkillRouting('mcm-figure'), /nature-figure/);
  assert.ok(!renderSkillRouting('mcm-figure').includes('section-draft'));
  assert.equal(OPTIONAL_ROLES['mcm-code-lead'].requires_explicit_enable, true);
});

test('current prompt sources retain pause, small-context, role readback and honest tool boundaries', async () => {
  const shared = await readFile(new URL('shared.md', promptsRoot), 'utf8');
  assert.match(shared, /context pack/);
  assert.match(shared, /最新暂停决定/);
  assert.match(shared, /实际 agent_id/);
  assert.match(shared, /部分 Team 入口会继承/);
  assert.match(shared, /运行端可能叠加全局/);
  assert.match(shared, /实际共享根激活池/);
  assert.match(shared, /不把每根限额称为 Desktop\/Host 全局上限/);
  assert.match(shared, /mcm_root_pool_capture/);
  assert.ok(!shared.includes('maxActiveSubagents=8'));
  const programmer = await readFile(new URL('mcm-programmer.md', promptsRoot), 'utf8');
  assert.match(programmer, /深度 1/);
  assert.match(programmer, /深度 2/);
  assert.match(programmer, /P1/);
  assert.match(programmer, /P2/);
  const code = await readFile(new URL('mcm-code-lead.md', promptsRoot), 'utf8');
  assert.match(code, /默认不启用/);
  assert.match(code, /独立 verifier/);
});

test('paper prompts retain the user framework, early evidence figures and final-size typography', async () => {
  const lead = await readFile(new URL('mcm-paper-lead.md', promptsRoot), 'utf8');
  for (const term of ['问题重述与问题分析','问题假设与符号说明','模型建立与求解','灵敏性分析','模型评价','参考文献','附录','Summary','AI 报告']) assert.ok(lead.includes(term), term);
  assert.match(lead, /题问—主张—证据/);
  const figure = await readFile(new URL('mcm-figure.md', promptsRoot), 'utf8');
  assert.match(figure, /最终放入PDF的尺寸保持12pt/);
  assert.match(figure, /缩小后仍12pt/);
  assert.match(figure, /全篇仅允许两张定量图/);
  assert.match(figure, /config\/figure-style\.json/);
  assert.equal(/#[a-fA-F0-9]{6}/.test(figure), false, 'Source persona must not duplicate palette literals');
  assert.match(figure, /上游失效/);
  assert.match(figure, /不能自签独立验收/);
});

test('package version and generated metadata are tied to the routing source', async () => {
  const packageData = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'));
  assert.equal(packageData.version, SKILL_ROUTING.bundle_version);
  // No new SDK flags encode policy-only optional activation or skill permissions.
  const declarations = presetDeclarations(Object.fromEntries(ROLES.map((role) => [role.id, renderSkillRouting(role.id)])));
  const optional = declarations[0].insert.find((row) => row.config.id === 'mcm-code-lead');
  assert.ok(optional);
  assert.equal('optional' in optional.config, false);
  const text = JSON.stringify(declarations);
  assert.ok(!text.includes('"allowedSkills":'));
  const expected = createHash('sha256').update(JSON.stringify(SKILL_ROUTING)).digest('hex');
  assert.match(expected, /^[a-f0-9]{64}$/);
});

test('award reference routing is selective, versioned and not an SDK permission', () => {
  const library = SKILL_ROUTING.reference_library;
  assert.equal(library.catalog, 'references/award-patterns/catalog.json');
  assert.equal(library.minimum_patterns_per_task, 0);
  assert.equal(library.maximum_patterns_per_task, 2);
  assert.equal(library.fixed_task_inputs_required, true);
  assert.equal(library.actual_readback_required, true);
  assert.equal(library.retrieval_is_behavioral_not_a_permission, true);
  for (const role of ROLES) {
    const prompt = renderSkillRouting(role.id);
    assert.match(prompt, /真实角色/);
    assert.match(prompt, /无匹配则不加载/);
    assert.match(prompt, /实际读取后才登记/);
    assert.match(prompt, /path\/version\/sha256/);
    assert.match(prompt, /不是科学正确、视觉通过或获奖概率证明/);
  }
  const declared = JSON.stringify(presetDeclarations(Object.fromEntries(ROLES.map((role) => [role.id, renderSkillRouting(role.id)]))));
  assert.ok(!declared.includes('"reference_library":'), 'Behavioral reference policy must not leak into SDK fields');
});
