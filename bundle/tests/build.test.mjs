import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { buildBundle } from '../src/build.mjs';
import { ROLES, presetDeclarations, rolePlugins, emitYaml } from '../src/presets.mjs';
import { SKILL_ROUTING, OPTIONAL_ROLES } from '../src/skill-routing.mjs';

test('role graph preserves eleven IDs and adds one optional supervisor without leaf delegation', () => {
  assert.equal(ROLES.length, 12);
  const core = ['mcm-captain','mcm-model-lead','mcm-modeler','mcm-evidence','mcm-programmer',
    'mcm-verifier','mcm-paper-lead','mcm-writer','mcm-figure','mcm-typesetter','mcm-reviewer'];
  assert.deepEqual(ROLES.filter((role) => !role.optional).map((role) => role.id).sort(), core.sort());
  assert.equal(OPTIONAL_ROLES['mcm-code-lead'].enabled_by_default, false);
  const captain = ROLES.find((role) => role.id === 'mcm-captain');
  assert.equal(captain.children.length, 7);
  assert.ok(captain.children.includes('mcm-programmer'));
  assert.ok(captain.children.includes('mcm-code-lead'));
  for (const role of ROLES) {
    const plugins = rolePlugins(role, 'prompt');
    const delegation = plugins.filter((plugin) => plugin.name === '@deepseek-ai/dsh-tool-subagent');
    assert.equal(delegation.length, role.children ? 1 : 0, role.id);
    if (delegation.length) {
      assert.equal(delegation[0].config.provider, 'spawn');
      assert.equal(delegation[0].config.maxDepth, 2);
      assert.deepEqual(delegation[0].config.allowedAgentPresets, role.children);
    }
    assert.ok(plugins.some((plugin) => plugin.name === '@deepseek-ai/dsh-tool-subagent-control'));
    assert.equal(plugins.filter((plugin) => plugin.name === '@deepseek-ai/dsh-agent-tool-presentation').length, 1);
    assert.equal(plugins.find((plugin) => plugin.name === '@deepseek-ai/dsh-agent-tool-presentation').config.mode, 'ptc');
    assert.equal(plugins.filter((plugin) => plugin.id === 'mcm-audit').length, role.id === 'mcm-captain' ? 1 : 0);
    assert.equal(plugins.filter((plugin) => plugin.name === '@deepseek-ai/dsh-tool-ask-user').length, role.id === 'mcm-captain' ? 1 : 0);
    assert.deepEqual(plugins.find((plugin) => plugin.name === '@deepseek-ai/dsh-skill-filesystem').config, { watch: false });
    assert.equal(plugins.filter((plugin) => plugin.id === 'planning').length, role.id === 'mcm-captain' ? 1 : 0);
    if (role.id === 'mcm-captain') {
      const planning = plugins.find((plugin) => plugin.id === 'planning');
      assert.deepEqual(planning.isolate, { planMode: true });
      assert.equal(planning.config[0].name, '@deepseek-ai/dsh-plan-mode');
      assert.deepEqual(Object.keys(planning.config[0].config), ['section']);
    }
    assert.ok(!plugins.some((plugin) => /workflow|ralph|schedule|goal|plugin-manager/.test(plugin.name)));
  }
  assert.deepEqual(ROLES.find((role) => role.id === 'mcm-model-lead').children, ['mcm-modeler']);
  assert.deepEqual(ROLES.find((role) => role.id === 'mcm-paper-lead').children, ['mcm-writer', 'mcm-figure', 'mcm-typesetter']);
  assert.deepEqual(ROLES.find((role) => role.id === 'mcm-code-lead').children, ['mcm-programmer']);
  const byId = new Map(ROLES.map((role) => [role.id, role]));
  function walk(id, depth, ancestors = []) {
    assert.ok(!ancestors.includes(id), 'Role graph must be acyclic');
    assert.ok(depth <= 2, `${id} exceeds native maxDepth`);
    for (const child of byId.get(id).children || []) {
      assert.ok(byId.has(child));
      walk(child, depth + 1, [...ancestors, id]);
    }
  }
  walk('mcm-captain', 0);
});

test('build embeds source prompt bytes reproducibly and check detects prompt drift', async () => {
  const root = await mkdtemp(join(tmpdir(), 'mcm-build-'));
  try {
    await mkdir(join(root, 'prompts'));
    await mkdir(join(root, 'src'));
    await writeFile(join(root,'src','figure-style.json'),await readFile(new URL('../src/figure-style.json',import.meta.url)));
    await writeFile(join(root, 'prompts', 'shared.md'), '# Shared\nTask rules.');
    for (const role of ROLES) await writeFile(join(root, 'prompts', `${role.id}.md`), `# ${role.id}\nUse evidence, cite results.`);
    const first = await buildBundle(root);
    assert.equal(first.role_count, 12);
    assert.equal(first.bundle_version, '0.2.2');
    const text = await readFile(join(root, 'cordis.patch.yml'), 'utf8');
    assert.ok(text.includes('name: "@deepseek-ai/dsh-agent-preset"'));
    assert.ok(text.includes('prefix: |-'));
    assert.ok(text.includes('Task rules.'));
    assert.ok(text.includes('quantitative-figure → nature-figure'));
    const provenance = JSON.parse(await readFile(join(root, 'provenance.json'), 'utf8'));
    assert.equal(provenance.bundle_version, '0.2.2');
    assert.equal(provenance.role_count, 12);
    assert.equal(provenance.optional_roles['mcm-code-lead'].enabled_by_default, false);
    assert.match(provenance.skill_routing_sha256, /^[a-f0-9]{64}$/);
    for (const name of ['runtime-guard-core.mjs','runtime-guard-plugin.mjs','root-pool-observer.mjs']) {
      const digest=createHash('sha256').update(await readFile(new URL(`../src/${name}`,import.meta.url))).digest('hex');
      assert.equal(provenance.runtime_guard_source_sha256[`src/${name}`],digest);
    }
    assert.equal(SKILL_ROUTING.bundle_version, provenance.bundle_version);
    assert.ok(text.includes("disabled: !!js process.platform === 'win32'"));
    assert.equal(text.includes('promptFile'), false);
    await buildBundle(root, { check: true });
    await buildBundle(root);
    assert.equal(text, await readFile(join(root, 'cordis.patch.yml'), 'utf8'));
    // A style change must invalidate the generated role configuration, not only a document.
    const style = JSON.parse(await readFile(join(root,'src','figure-style.json'),'utf8'));
    style.palette.blue = '#125588';
    await writeFile(join(root,'src','figure-style.json'),JSON.stringify(style));
    await assert.rejects(buildBundle(root, { check: true }), /stale/);
    await buildBundle(root);
    assert.ok((await readFile(join(root,'cordis.patch.yml'),'utf8')).includes('blue=#125588'));
    await writeFile(join(root, 'prompts', 'mcm-modeler.md'), 'Changed actual instructions');
    await assert.rejects(buildBundle(root, { check: true }), /stale/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('native declaration format and generated YAML retain list structure and safe scalar quoting', () => {
  const data = presetDeclarations(Object.fromEntries(ROLES.map((role) => [role.id, 'line 1\nline 2: "quote"'])));
  assert.equal(data[0].insert[0].config.id, 'mcm-captain');
  const text = emitYaml(data);
  assert.ok(text.startsWith('- insert:\n    - id:'));
  assert.ok(text.includes('line 2: "quote"'));
  assert.ok(!text.includes('[object Object]'));
  for (const declaration of data[0].insert) {
    assert.deepEqual(Object.keys(declaration.config).sort(), ['description','id','name','order','plugins']);
    assert.equal('allowedSkills' in declaration.config, false);
    assert.equal('enabledByDefault' in declaration.config, false);
  }
});
