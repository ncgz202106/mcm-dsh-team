import { mkdir, readFile, writeFile, symlink, rm, cp, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const auditDir = dirname(fileURLToPath(import.meta.url));
const teamDir = dirname(auditDir);
const workspace = resolve(teamDir, '../..');
const desktopRoot = process.argv.find((arg) => arg.startsWith('--desktop-root='))?.slice('--desktop-root='.length) ?? 'E:/dsh desktop';
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
const work = join(workspace, 'work', 'mcm-host-smoke', stamp);
const home = join(work, 'home');
const project = join(work, 'project');
const reportPath = process.argv.find(arg=>arg.startsWith('--report='))?.slice('--report='.length) ?? join(auditDir, 'native-runtime-smoke.json');
await mkdir(dirname(reportPath), { recursive: true });
const bundlePath = process.argv.find(arg=>arg.startsWith('--bundle-root='))?.slice('--bundle-root='.length) ?? join(teamDir, 'bundle');
const fingerprintFiles = ['package.json', 'cordis.patch.yml', 'provenance.json', ...(await readdir(join(bundlePath,'src'))).filter(name=>/\.(mjs|json)$/.test(name)).sort().map(name=>`src/${name}`)];
const guardReportPath = process.argv.find(arg=>arg.startsWith('--guard-report='))?.slice('--guard-report='.length) ?? join(dirname(reportPath),'guard-native-runtime.json');
const fixtureName = process.argv.find(arg=>arg.startsWith('--fixture='))?.slice('--fixture='.length) ?? 'native-fixture.mjs';
if(!/^(?:native-fixture|guard-native-fixture)\.mjs$/.test(fixtureName))throw new Error('Only packaged isolated native fixtures are supported');
const fixtureSha256=createHash('sha256').update(await readFile(join(auditDir,fixtureName))).digest('hex');
const launcherSha256=createHash('sha256').update(await readFile(fileURLToPath(import.meta.url))).digest('hex');
const fingerprints = {};
for (const path of fingerprintFiles) fingerprints[path] = createHash('sha256').update(await readFile(join(bundlePath, path))).digest('hex');
const runtimeRoot = join(desktopRoot, 'resources', 'app.asar', 'dsh');
const executable = join(desktopRoot, 'DeepSeek Harness.exe');
const entry = join(runtimeRoot, 'node_modules', '@deepseek-ai', 'dsh-desktop-host', 'lib', 'cli.js');
const environment = {};
for (const key of ['PATH', 'Path', 'SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'ComSpec', 'PATHEXT', 'ProgramFiles', 'ProgramFiles(x86)']) if (process.env[key] !== undefined) environment[key] = process.env[key];
Object.assign(environment, { ELECTRON_RUN_AS_NODE: '1', DSH_HOME: home, DSH_AGENTS_HOME: join(home, 'agents'), DSH_PERMISSION_MODE: 'workspace-write' });
await cp(join(teamDir, 'project-template'), project, { recursive: true, filter: (p) => !p.includes('__pycache__') });
await mkdir(join(home, 'skills'), { recursive: true });
const skillRoot = process.argv.find(arg=>arg.startsWith('--skills-root='))?.slice('--skills-root='.length) ?? join(process.env.USERPROFILE, '.dsh', 'skills');
for (const name of ['nature-figure', 'nature-academic-search', 'nature-ref-verifier', 'nature-shared']) {
  await symlink(join(skillRoot, name), join(home, 'skills', name), process.platform === 'win32' ? 'junction' : 'dir');
}
await cp(join(auditDir, 'public-source-probe.py'), join(project, 'scripts', 'public-source-probe.py'));

async function run(args, label) {
  const result = await new Promise((resolveRun, reject) => {
    const child = spawn(executable, ['--expose-internals', entry, ...args], { cwd: project, env: environment, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '', stderr = '';
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    const timer = setTimeout(() => { child.kill(); reject(new Error(`${label} exceeded 120 seconds`)); }, 120000);
    child.on('error', (error) => { clearTimeout(timer); reject(error); });
    child.on('exit', (code) => { clearTimeout(timer); resolveRun({ code, stdout, stderr }); });
  });
  await writeFile(join(work, `${label}.stdout.log`), result.stdout);
  await writeFile(join(work, `${label}.stderr.log`), result.stderr);
  return result;
}

const init = await run(['--profile', 'mcm-smoke', '--from-default-profile', 'headless', '--dump-default-config'], 'initialize');
if (init.code !== 0) throw new Error(`Isolated profile initialization failed; see ${work}`);
const profile = join(home, 'profiles', 'mcm-smoke');
const manifestPath = join(profile, 'package.json');
const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
manifest.dependencies ??= {};
manifest.dependencies['dsh-mcm-team'] = `file:${bundlePath.replaceAll('\\', '/')}`;
manifest.dsh.profile.bundles.push('dsh-mcm-team');
await writeFile(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
await mkdir(join(profile, 'node_modules'), { recursive: true });
await symlink(bundlePath, join(profile, 'node_modules', 'dsh-mcm-team'), process.platform === 'win32' ? 'junction' : 'dir');
const disable = ['headless-startup', 'headless-runner', 'session-title-llm', 'session-telemetry-otel', 'llm-pi-ai', 'llm-deepseek', 'llm-deepseek-account', 'web-search-deepseek', 'web-deepseek-api', 'tool-working-directory', 'tool-bash', 'tool-pwsh', 'tool-fs', 'tool-fs-search', 'tool-jobs', 'agent-instructions', 'skill-filesystem', 'tool-skill', 'command-goal', 'plan-mode', 'compaction-basic', 'command-compact', 'tool-result-pruner', 'tool-subagent-control', 'tool-subagent-list-agents', 'tool-subagent', 'tool-subagent-fork', 'workflow-ptc', 'tool-workflow', 'tool-todo', 'tool-goal', 'tool-web'];
const patch = disable.map((id) => ({ id, disabled: true }));
patch.push({ insert: [
  { id: 'mcm-smoke-preset-registry', name: '@deepseek-ai/dsh-agent-preset-registry', config: { default: 'mcm-captain' } },
  { id: 'mcm-smoke-model-selection', name: '@deepseek-ai/dsh-tool-subagent/model-selection-settings', config: { enabled: false, allowedModels: [] } },
  { id: 'mcm-smoke-fixture', name: join(auditDir, fixtureName), config: { project, reportPath, runtimeRoot, work, bundlePath, fingerprints, skillRoot, fixturePath:join(auditDir,fixtureName),fixtureSha256,launcherPath:fileURLToPath(import.meta.url),launcherSha256,guardReportPath,python: 'C:/Program Files/Python314/python.exe' } }
] });
await writeFile(join(profile, 'cordis.patch.yml'), JSON.stringify(patch, null, 2));
const smoke = await run(['--profile', 'mcm-smoke'], 'runtime');
if (smoke.code !== 0) {
  // Keep the failure visible; do not replace the last successful report with a success claim.
  await writeFile(join(auditDir, 'native-runtime-smoke-failure.json'), JSON.stringify({ status: 'failed', attempted_at: new Date().toISOString(), work, code: smoke.code, diagnostics: `${work}/runtime.stderr.log` }, null, 2));
  console.error(smoke.stderr.slice(-6000));
  throw new Error(`Native smoke failed (${smoke.code}); see ${work}`);
}
const report = JSON.parse(await readFile(reportPath, 'utf8'));
for (const [path, expected] of Object.entries(fingerprints)) {
  if (createHash('sha256').update(await readFile(join(bundlePath, path))).digest('hex') !== expected) {
    report.status = 'stale'; report.stale_reason = `Bundle changed during test: ${path}`;
    await writeFile(reportPath, JSON.stringify(report, null, 2));
    throw new Error(report.stale_reason);
  }
}
await rm(join(auditDir, 'native-runtime-smoke-failure.json'), { force: true });
console.log(JSON.stringify({ status: report.status, runtime: report.runtime_version, checks: report.checks.length, report: reportPath, work }));
