import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { resolve, join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { ROLES } from '../../bundle/src/presets.mjs';
import { SKILL_ROUTING, renderSkillRouting } from '../../bundle/src/skill-routing.mjs';

export const ADAPTER_VERSION = '0.1.0-candidate';
const ROOT = resolve(fileURLToPath(new URL('../../', import.meta.url)));
const digest = b => createHash('sha256').update(b).digest('hex');
const norm = s => s.replace(/\r\n/g, '\n');

/** Replace an explicitly identified paragraph, retaining every other source byte. */
export function paragraph(text, prefix, replacement) {
  const blocks = text.split('\n\n');
  const matches = blocks.map((v,i) => v.startsWith(prefix) ? i : -1).filter(i => i >= 0);
  if (matches.length !== 1) throw new Error(`Projection drift: expected one paragraph: ${prefix}`);
  blocks[matches[0]] = replacement;
  return blocks.join('\n\n');
}
export function exact(text, before, after) {
  if (text.split(before).length !== 2) throw new Error(`Projection drift: expected one exact span: ${before}`);
  return text.replace(before, after);
}

const runtimeRules = `# Codex 美赛团队运行层

根 Codex 是唯一实际调度者、全局登记者与交付整合者。12类科学职责保持，所有实际子 Agent 均由根创建，物理深度1；主管提出任务和验收建议，不自行创建后代。身份以真实工具回执为准，任务名称不能证明原生角色已加载。

先读项目AGENTS、相关任务context pack和当前工具schema。继承当前模型和权限；本包不改变provider、访问模式或安全设置。实际工具缺角色选择/身份/拦截观测时报告unknown，strict预检不通过；配置文件存在不构成运行验收。

使用 python scripts/codex_control.py --root <项目根> capabilities 和 preflight；派发前须登记唯一任务、输入引用、写范围和验收，执行claim记录唯一attempt。其余参数以 --help 为准。交付使用deliver，接收使用accept，保护与恢复使用protect/recover。也可经现有mcm.py的codex子命令转发。

子任务仅写各自授权目录，不改全局登记/主稿/其他作者源码。主管提出集成补丁，唯一文件负责人整合。成果必须读回路径、版本、真实哈希和依赖；作者不自签独立通过。非作者报告绑定同一候选，科学/视觉/编译验收分别记录。

容量以当前工具可确认的限制和项目预算为界，不硬编码Host上限；未知容量串行，空闲不等于已释放。根持有实际AgentID和任务对应关系。禁止用新的后台Host、其他模型服务或轮询群聊绕过限制。

只传任务摘要和文件引用，独立建模/审阅请求干净上下文，不继承作者完整草稿历史。暂停时停止新派发、请求已知子任务中断并核状态；后到交付仅待查，不能接收。恢复依据真实用户决定，再核验保护快照、输入、所有权和有效批次。

本包提供协作检查，不能防止同权限任意shell绕过。只有实际工具路径拦截测试通过才登记hook_verified；未覆盖路径、失败或未知均保留。人工H0/H1/H2/H3永不由技术测试、等待、角色自报或synthetic演练生成。
`;

function common(source) {
  let s = source;
  s = exact(s, 'PTC 是 DSH 的 Programmatic Tool Calling，以当前 run_code 及其生成的工具 schema 为准。', '程序化工具调用仅使用当前Codex实际提供的工具接口，不引入另一个Host。');
  s = exact(s, '无法读回真实 preset 或有效工具时如实 unknown', '无法读回原生角色或有效工具时如实记录 unknown');
  const start = s.indexOf('## 唯一调度、真实角色与容量\n');
  const end = s.indexOf('## 单写入者与成果\n');
  if (start < 0 || end <= start) throw new Error('Shared runtime section drift');
  s = s.slice(0,start) + '## 唯一调度、真实角色与容量\n\n遵循上方Codex运行层：根唯一实际派发，主管保留科学职责，所有子角色禁止再派生。原生角色、容量、hook与权限分别核验，不从角色名推断。\n\n' + s.slice(end);
  const gate = '\n# 原生派发硬门禁（v0.2 安装验收修复）';
  if (!s.includes(gate)) throw new Error('Shared native gate boundary drift');
  s = s.slice(0, s.indexOf(gate));
  return s;
}

function roleText(id, source) {
  let s = source;
  const replace = (prefix, replacement) => { s = paragraph(s, prefix, replacement); };
  if (id === 'mcm-captain') {
    replace('你是 DSH 根队长', '你是Codex根队长，负责全局任务、版本、容量、人工关口和交付。所有实际子角色由你创建，主管负责专业拆解和整合；你实质参与的成果另由非作者审阅。重大科学决定和发布仍归用户，不另建第二份任务板。');
    s = exact(s, '每个检查点只向 Codex/用户交关键结论', '每个检查点只向用户交关键结论');
    replace('captain 专用 mcm_archive_audit', '于H0/H1/H2/H3候选及回退保存项目快照、固定成果清单和可见任务用途记录。只归档实际可读取内容，不导出内部推理或凭据；缺失会话、附件或使用记录必须明确报告，不推断已经人工核验。');
    replace('code-lead 只在当前项目明确启用', 'code-lead仅在项目明确启用且确有集成需求时分配专业统筹任务；所有programmer仍由你创建。新实例核对原生角色选择能力、实际身份与可观察配置；不能核验则strict预检阻断，不用任务名称替代原生角色。');
    replace('预算来自项目与 Host', '预算来自当前Codex实际可观察的会话限制和项目配额。保留应急位置，等待实例仍按实际计数计入；容量未知时串行，记录未知范围。只有真实终态才能释放名额，不把中断一轮当作关闭实例。');
    replace('model-lead 可派最多三位 modeler', 'model-lead提出最多三位modeler任务，paper-lead提出writer/figure/typesetter任务，可选code-lead提出programmer任务；均由根统一创建。各阶段轮换角色，不常开全部实例。');
  } else if (id === 'mcm-model-lead') {
    replace('你统一题意', '你统一题意、数学架构、跨问接口和模型选择。你直属根队长；提出最多三位mcm-modeler的独立任务，由根实际派发。你不创建任何后代。');
    s = exact(s, '向三位建模手发送同一题目和基础证据', '安排独立盲写，请根队长向三位建模手发送同一题目和基础证据');
  } else if (id === 'mcm-code-lead') {
    replace('你是 captain 的一级孩子', '你直属根队长，仅在明确启用可选角色且存在集成任务时工作。你为programmer准备分包，由根实际创建；你不派发任何Agent。可安装不等于应启动，未启用或配额不明时回报根。');
    s = exact(s, '子 Agent 原生 spawn 显式选 mcm-programmer，读回实际身份，不用 Team 名字替代预设。', '将mcm-programmer任务建议交根队长，由根核对原生角色与真实身份后派发。');
  } else if (id === 'mcm-paper-lead') {
    replace('你是 captain 的一级孩子', '你直属根队长，提出mcm-writer、mcm-figure、mcm-typesetter任务，由根实际创建。你负责论证、结构、篇幅、图表取舍及唯一主稿整合，不自行创建后代，不代独立审阅或用户放行。');
    s = exact(s, '三类孩子并开前计入你等待的槽位；容量不足轮换。', '三类执行角色由根统一核对容量后启动；你等待时也按实际占用计数，容量不足轮换。');
  } else if (id === 'mcm-modeler') {
    s = exact(s, '你由建模负责人派发，不得再派子 Agent。', '你接收建模负责人拟定、根队长实际派发的任务，不得再派子Agent。');
  } else if (id === 'mcm-writer') {
    s = exact(s, '你由论文负责人派发，不得再派子 Agent。', '你接收论文负责人拟定、根队长实际派发的任务，不得再派子Agent。');
  } else if (id === 'mcm-programmer') {
    s = exact(s, '你可直属队长（深度 1），或由明确启用的编程统筹派发（深度 2）；两种情况下均为叶子，不再派任何 Agent。', '你直属根队长；可接受编程统筹拟定的分包，实际派发仍由根执行。你不再派任何Agent。');
  } else if (id === 'mcm-figure') {
    s = exact(s, '你由 paper-lead 派发，深度2叶子，不再派 Agent。', '你接收paper-lead拟定、根队长实际派发的任务，不再派Agent。');
  } else if (id === 'mcm-typesetter') {
    s = exact(s, '你由 paper-lead 派发，深度2叶子，不再派Agent。', '你接收paper-lead拟定、根队长实际派发的任务，不再派Agent。');
  }
  if (/DSH|agent_preset|mcm_archive_audit|深度\s*2|深度2|可派最多|可派 writer|可派 mcm-/u.test(s)) throw new Error(`Unprojected runtime instruction in ${id}`);
  return s;
}

function projectAgents(source) {
  let s = source;
  s = exact(s, '3. 读取本文件、`protocols/` 中对应条目及当前 DSH 真实工具 schema。公共提示词已由预设构建器合成，工具名和参数仍以运行端为准。', '3. 读取本文件、相关protocol和Codex实际工具schema。运行约束由Codex适配层生成；角色配置文件存在不等于已加载。');
  const lines = s.split('\n');
  const p1 = lines.findIndex(l=>l.startsWith('- 新项目计划默认常态7槽'));
  const p2 = lines.findIndex(l=>l.startsWith('- 深度最多2'));
  if(p1<0||p2<0) throw new Error('Project topology drift');
  lines[p1] = '- 根Codex队长唯一实际派发，按已知会话容量与项目预算排队，保留应急位置；未知容量串行。容量事实、项目配额、角色配置与工具权限分别记录。';
  lines[p2] = '- 物理派发深度1。主管拟定任务，根创建所有执行角色；三位建模手初期盲写，programmer默认两个互不覆盖实例，可选code-lead默认关闭。独立verifier不兼任被验成果作者。';
  s = lines.join('\n');
  s = paragraph(s, 'Codex在检查点担任技术总监', 'Codex根队长负责全部日常调度与全局登记；独立审阅由非作者角色承担。主管只整合授权文件并提出下游任务。不能把检查点意见当作人工批准。');
  s = exact(s, '`python scripts/mcm.py context-pack TASK_ID`', '`python scripts/mcm.py --root <项目根> context-pack TASK_ID`');
  return s + '\n\n## Codex能力与接收入口\n\n' + runtimeRules + '\n';
}

function projectReadme(source) {
  let text = exact(source, '不会调用 DSH、创建会话', '不会创建 Codex 会话');
  const begin = text.indexOf('## 容量与 DSH 运行时\n');
  const end = text.indexOf('## 快照、故障恢复和截止时间\n');
  if (begin < 0 || end <= begin) throw new Error('Project README runtime section drift');
  const runtime = '## Codex 协作能力\n\n从项目根运行 `python scripts/mcm.py codex capabilities` 和 `python scripts/mcm.py codex preflight`。实际角色与工具拦截待验时，严格预检阻断正式派发。详见 [能力与验收范围](protocols/08-codex-readiness.md)。恢复前使用 `python scripts/mcm.py codex recover` 核查事务和写锁。\n\n';
  text = text.slice(0, begin) + runtime + text.slice(end);
  return exact(text, '、7+1 容量、', '、容量边界、');
}

export async function build({ root = ROOT, out = join(ROOT,'adapters/codex/generated'), check = false } = {}) {
  const inputs = {}, outputs = {};
  const load = async path => { const bytes = await readFile(join(root,path)); inputs[path] = digest(bytes); return norm(bytes.toString('utf8')); };
  const add = (path, value) => { outputs[path] = typeof value === 'string' ? value : JSON.stringify(value,null,2)+'\n'; };
  await load('adapters/codex/build.mjs');
  await load('bundle/src/presets.mjs');
  await load('bundle/src/skill-routing.mjs');
  const style = JSON.parse(await load('bundle/src/figure-style.json'));
  const overlayStyle = JSON.parse(await load('skill-overlays/nature-figure/assets/mcm-figure-style.json'));
  if(JSON.stringify(style)!==JSON.stringify(overlayStyle)) throw new Error('Figure style differs from the common source');
  const shared = common(await load('bundle/prompts/shared.md'));
  const sourceRoles = [];
  for(const role of ROLES) {
    const body = roleText(role.id, await load(`bundle/prompts/${role.id}.md`));
    const instructions = runtimeRules + '\n' + shared + '\n' + body + '\n' + renderSkillRouting(role.id);
    if(/DSH|agent_preset|mcm_runtime_readback|mcm_dispatch_preflight|run_code|mcm_archive_audit/.test(instructions)) throw new Error(`Platform residue in ${role.id}`);
    add(`project/.codex/agents/${role.id}.toml`, `# Generated; source role: bundle/prompts/${role.id}.md\nname = ${JSON.stringify(role.id)}\ndescription = ${JSON.stringify(role.id==='mcm-captain' ? 'MCM root coordinator; native role readiness and evidence gates.' : role.description)}\ndeveloper_instructions = ${JSON.stringify(instructions)}\n`);
    sourceRoles.push({id:role.id, logical_children:role.children||[], physical_parent:role.id==='mcm-captain'?null:'mcm-captain', may_spawn:role.id==='mcm-captain', optional:!!role.optional});
  }
  add('project/AGENTS.md', projectAgents(await load('project-template/AGENTS.md')));
  add('project/README-example.md', projectReadme(await load('project-template/README-example.md')));
  const latex = JSON.parse(await load('project-template/paper/provenance/latex-project.json'));
  latex.template.path = 'paper/provenance';
  add('project/paper/provenance/latex-project.json', latex);
  add('project/protocols/01-runtime-and-dispatch.md', runtimeRules);
  let review = await load('project-template/protocols/04-review-and-human-gates.md');
  review = exact(review, 'Codex可以给独立技术意见，DSH队长统一分诊', '非作者角色给独立技术意见，Codex根队长统一分诊');
  add('project/protocols/04-review-and-human-gates.md', review);
  const config = JSON.parse(await load('project-template/config/runtime.json'));
  Object.assign(config,{runtime_provider:'codex',runtime_source:'Actual Codex tool observations; this CLI does not spawn agents or authenticate native capabilities',normal_slots:2,reserve_slots:1,max_nested_depth:1,dispatch_route:'codex_root_only_verified_native',default_mode:'strict',runtime_snapshot:null,notes:'Planning values are not Host facts. Unknown capacity is serial. Native role binding and hook coverage require independent runtime evidence; same-permission agents are not OS isolated.',capabilities:{native_role_selection:{verified:false},tool_hook:{verified:false}}});
  config.require_section_visual_coverage = true;
  add('project/config/runtime.json',config);
  add('project/config/codex-roles.json',{format_version:1,adapter_version:ADAPTER_VERSION,roles:sourceRoles});
  add('project/config/skill-routing.json',SKILL_ROUTING);
  add('project/protocols/08-codex-readiness.md',await load('adapters/codex/references/readiness.md'));
  for (const name of ['mcm.py', 'codex_control.py', 'codex_hook.py', 'paper.py', 'section_visuals.py']) {
    await load(`project-template/scripts/${name}`);
  }
  await load('project-template/templates/section-visual-map.json');
  await load('project-template/protocols/07-argument-and-visual-design.md');
  for(const name of ['SKILL.md','references/start.md','agents/openai.yaml']) add(`skill/${name}`,await load(`adapters/codex/skill/${name}`));
  for (const name of ['o-award-framework.md', 'chart-reference.md']) {
    const reference = await load(`project-template/resources/mcm-skills/${name}`);
    add(`skill/references/${name}`, reference);
    add(`project/resources/mcm-skills/${name}`, reference);
  }
  const chartGallery = await load('adapters/codex/skill/references/chart-gallery.html');
  add('skill/references/chart-gallery.html',chartGallery);
  const overlay = JSON.parse(await load('skill-overlays/manifest.json'));
  for(const skill of overlay.skills) {
    for(const rel of [overlay.reference,...(overlay.resources?.[skill]||[])]) {
      const text = await load(`skill-overlays/${skill}/${rel}`);
      add(`skill/references/skills/${skill}/${rel}`,text);
      add(`project/resources/mcm-skills/${skill}/${rel}`,text);
    }
  }
  add('skill/references/readiness.md',await load('adapters/codex/references/readiness.md'));
  add('skill/references/source-notice.md','These are original MCM adaptation references and synthetic examples. Full upstream third-party skills are not bundled. Discover installed skills before use; absence is a reported dependency gap.\n');
  const generated = Object.fromEntries(Object.entries(outputs).map(([p,v])=>[p,digest(v)]));
  add('manifest.json',{format_version:1,adapter_version:ADAPTER_VERSION,status:'candidate_native_runtime_pending',sources:inputs,files:generated,role_count:ROLES.length,native_runtime_verified:false,hook_runtime_verified:false});
  for(const [path,content] of Object.entries(outputs)) {
    const target=join(out,path);
    if(check) {
      const current=await readFile(target,'utf8').catch(()=>null);
      if(current!==content) throw new Error(`Generated file stale or missing: ${path}`);
    } else { await mkdir(dirname(target),{recursive:true}); await writeFile(target,content,'utf8'); }
  }
  return {files:Object.keys(outputs).length,roles:ROLES.length,status:'candidate_native_runtime_pending',out};
}

if (process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
  const i=process.argv.indexOf('--out');
  console.log(JSON.stringify(await build({check:process.argv.includes('--check'),...(i>=0?{out:resolve(process.argv[i+1])}:{})})));
}
