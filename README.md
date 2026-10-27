# MCM A/B/C · DSH PTC 多 Agent v0.2.2 候选

本分支在冻结的0.2.1上增加优秀论文模式库、可运行图表与页面小样，并进行真实模型对照。当前尚未正式安装或宣称完整A题通过；已安装稳定版仍为0.2.1。

- [本轮改动、验收安排与边界](docs/v0.2.2研究与验收.md)
- [9篇案例与11条按需模式](project-template/references/award-patterns/catalog.json)
- [六类合成图与四类页面的可运行入口](gallery/README.md)
- [六页合成页面PDF](gallery/pages/page-examples.pdf)（不是完整A题论文）
- [本版源码与软件检查](audit/v0.2.2/source-verification.json)；真实模型、视觉和人工批准分别留证，不能由该检查器代签。
- [待审交付依赖修复与最新软件检查](docs/v0.2.2复验依赖修复.md)：旧执行依赖仍须批准；显式复验依赖可读取已交付固定版本，容量未知仍拒绝。历史原生运行时报告不证明这次新代码已部署。

以下保留稳定版0.2.1的安装与历史说明；本候选通过全部发布条件后再更新部署记录。

# MCM A/B/C · DSH PTC 多 Agent v0.2.1

当前维护版本为 **0.2.1**。历史工作目录名保留不变，实际版本以 bundle/package.json 为准。

本次新增五个专项Skill的MCM条件分支、三类论证内容卡、多面板证据设计与叙事审阅；图表默认色号改为单一配置源。12角色、默认两名编程手、论文→写作/图表/排版、PTC和原生派发门禁保持。

- [v0.2.1更新、Skill安装与恢复说明](docs/v0.2.1更新说明.md)
- [本版软件与源码检查](audit/v0.2.1/verification.json)
- [实际安装与独立复核记录](audit/v0.2.1/deployment.json)（已安装0.2.1；42项安装与证据绑定检查通过）
- [角色与Skill源码](skill-overlays/manifest.json)
- [图表组合演示](audit/v0.2.1/demo/evidence-panels.png)（合成数据）
- 新会话使用“美赛 · 队长”和[启动词](启动词.txt)，填唯一项目根；原暂停演练不因升级恢复。

重新安装或维护时，先运行 `python tools/verify-v021.py --run-tests`。DSH插件通过官方更新器安装，需正常退出桌面版，不能热覆盖。实际安装与Skill部署状态以本版deployment.json为准，源码或单元测试通过不自证安装成功。

公开仓库的后续改动按[同步约定](docs/GitHub同步.md)检查、提交和推送。新报告去除本机路径；旧版公开历史未在本次改写或追认脱敏。

<details>
<summary>v0.2.0 历史交付与使用说明（以下旧报告不证明当前源码通过）</summary>

# MCM A/B/C · DSH PTC 多 Agent v0.2.0

中文协作、英文论文。DSH队长是唯一日常内部调度者；Codex在模型路线、核心结果、论文整合三个检查点提供技术审阅。PTC指Programmatic Tool Calling。本版用于新启动会话，原已暂停演练不恢复、不迁移、不覆盖。

## 新版变化

- 保留原11个角色ID，新增默认不启动的mcm-code-lead，共12类预设。
- 编程默认两个实例：核心求解、实验与结果导出；第三实例或主管只按实际工程包启用。
- 论文负责人派发写作、科研图表、排版；图多时拆定量与方法示意两个图表实例。
- 按任务加载专项Skill，排除shumo2、shumo-core等全流程总控的直接或间接自动调用。
- 小上下文、单写入者、成果读回、当前依赖闭包、H2结果与H3最终PDF分离。
- 统一图表美学，编译、内容完整与视觉验收分别留证。
- 原生派发门禁：真实角色读回、任务与新鲜容量证据、一次许可；暂停、未知或过期时直接拒绝。

实际版本见bundle/package.json，验证见audit/及安装收据。旧版报告不证明新版通过；合成演练不构成参赛结果。

## 先看交付成果

- [七页合成演练PDF](rehearsal-v2/build/paper/demo.pdf)：用户结构、原生公式、方法总览、结果对照、灵敏性和参数包络；示范排版与管线，不能直接参赛提交。
- [12角色与检查点架构](diagrams/01-role-architecture.png)、[实际通信与成果依赖](diagrams/02-runtime-communication.png)、[竞赛与整改闭环](diagrams/03-workflow-review.png)。同目录保留SVG、JSON源和可缩放HTML。
- [图表样例目录](rehearsal-v2/figures/figure-demo/)：每图PDF、SVG、300dpi PNG、数据、契约与检查记录。
- [当前验证报告](audit/verification.json)及[独立架构视觉记录](audit/architecture-visual-v2.json)。107项Python、37项Node和10项安装故障注入通过；[主运行机制9项](audit/native-runtime-smoke.json)与[门禁10项](audit/guard-native-runtime.json)使用真实DSH和确定性模型夹具，最终报告均绑定当前安装目录的字节，不能冒充外部模型自主执行验收。
- [官方npm打包的插件](dsh-mcm-team-0.2.0.tgz)，完整项目模板和文档则保留在本包中。

## 安装与更新

适配已检查的DSH 0.2.1-rc.2。候选测试完成后，保存工作并正常退出DSH。官方命令行修改profile，不能与活跃Host同时更新；脚本不会强制关闭桌面版。

从本包根目录先只读预检，再执行更新：

```powershell
pwsh -File tools/update-dsh.ps1 -DshCli 'E:\dsh desktop\resources\runtime\cli\bin\dsh.cmd' -CheckOnly
pwsh -File tools/update-dsh.ps1 -DshCli 'E:\dsh desktop\resources\runtime\cli\bin\dsh.cmd'
```

更新器备份旧插件及有关profile配置，校验候选字节，再用官方安装命令更新同一插件ID，保留其他插件。安全更新和恢复限定当前用户.dsh/plugins/dsh-mcm-team；其他位置须先核对原生安装布局，不能用自定义路径绕过检查。

完整插件树与备份记录相对路径、存在状态和字节哈希；恢复还会核对安装后profile和实际依赖解析，拒绝覆盖后来发生的用户修改。-PluginRoot保留接口，但不允许借此写任意目录。回滚可先用restore-dsh.ps1的-CheckOnly，只读核验后再正常退出DSH执行。

首次安装用tools/install-dsh.ps1及相同-DshCli参数；检测到现有标准安装时转入可回滚更新器。首次安装链接本包bundle目录，因此请保留稳定路径。操作说明见[更新与回滚](docs/更新与回滚.md)。

首次目录链接不由当前严格标准目录更新器自动迁移；非常规布局须先单独核对，不强行覆盖。

启动DSH后核对版本0.2.0、12个“美赛 · ”角色和有效配置；建立隔离新会话，验证实际角色、派发、技能执行和成果。命令成功不等于运行时验收通过；本README不自证已安装成功。

v0.2.0历史安装目录为当前用户的 `.dsh/plugins/dsh-mcm-team`。当时的收据保留在仓库外本机备份中；[非作者安装核验](audit/installed-verification.json)的14项检查确认当时29份安装文件、配置/依赖保留、12角色及新工具绑定，以及当时安装字节的主9项与门禁10项证据。旧收据状态及证据入口见[历史安装摘要](audit/installation-summary.json)。用户profile备份不混入公开包。

最新备份回到本次门禁修订前的0.2.0；20261025-221327-045仍保存原0.1.0。两轮之间profile的cordis.patch.yml已有变化，第二段回到0.1.0的预检可能拒绝，须核对并保留用户后续配置，不能承诺直接连续执行两次恢复。详见[更新与回滚](docs/更新与回滚.md)。

[早先桌面真实模型小演练](audit/live-model-verification.json)已实际生成四类图并调用专项技能，保留DEV-01“容量准入失败仍派发”的历史偏差。当前门禁修复已由真实工具管线和[桌面外部模型负向复验](audit/guard-live-verification.json)分别验证：容量未知预检拒绝、无许可原生派发拒绝、实际零子会话，40个保护文件与4个人工关口保持。负向检查通过不等于完整自主建模通过。

## 如何使用

已有项目不必重复创建副本或重装环境。新演练建议使用独立目录：

```powershell
pwsh -File tools/new-project.ps1 -Destination 'D:\MCM\practice-01'
Set-Location 'D:\MCM\practice-01'
pwsh -File scripts/setup.ps1
.venv\Scripts\python.exe scripts/mcm.py --root . doctor
```

setup默认准备Python 3.12环境；已有兼容、经检查的环境可复用。题面放input/problem，附件放input/attachments；登记后的data/raw不覆盖，清洗另写data/processed。

在DSH新会话选择“美赛 · 队长”，工作目录设为项目绝对路径，粘贴启动词.txt并填写路径及状态。无需人工打开12个会话。原暂停演练只有用户另行明确恢复才可继续。

## 分工与专项技能

队长直管建模负责人、证据数据、编程、验证、论文负责人、审阅老师，必要时启用编程主管。主管按授权配额派叶子，最大深度2。原生spawn显式传agent_preset并读回真实角色/父级/深度/工具；Team成员名字不能代替角色绑定。

容量取项目预算与真实Host能力交集，保留应急位；等待主管仍占位。Team限制不等于Host容量。未知、过期或满额时先排队，确认实际释放后再派发。

管理角色先用mcm_runtime_readback核真实身份，再以mcm_dispatch_preflight核任务和容量并取得一次许可，随后原样调用原生subagent。许可最长60秒，不能并发重复使用；叶子及全局替代委派入口会在正常工具管线被拒绝。详见[原生派发门禁](docs/原生派发门禁.md)。配置上限和当前running数量都不能冒充实际占槽；缺少合格Host证据时停在诊断/队列，不自动创建“探针”。这是工具流程约束，不是OS隔离。

| 任务 | 主Skill | 边界 |
|---|---|---|
| 定量图、组合图 | nature-figure | 固定结果、项目后端与最终尺寸 |
| 方法/几何/流程示意 | fireworks-tech-graph | 可编辑矢量源 |
| 文献检索 | nature-academic-search | 具体证据缺口，不默认限定CNS |
| 引用核验 | nature-ref-verifier | 元数据与正文支持分别核查 |
| 合法全文获取 | nature-downloader | 按需，说明访问边界 |
| 英文写作与精简 | nature-writing、nature-polishing | generic路线，保留用户结构 |
| 统计审查 | nature-statistics | 适用的独立性与不确定性检查 |
| 独立审阅 | nature-reviewer | 用美赛要求，非期刊录用标准 |
| PDF页面检查 | pdf | 配合既有LaTeX构建 |

每任务选一个主Skill，按需读必要分支。已安装、已读取、实际执行、产物验收分别记录，缺依赖如实报告。Skill不能扩大任务、写入、派生或恢复权限。映射源bundle/src/skill-routing.mjs，项目导出config/skill-routing.json；详见[角色与专项Skill](docs/角色与专项Skill.md)。

## 论文与科研图表

固定功能顺序：题目/摘要/关键词；问题重述与分析；假设与符号；模型建立与求解；灵敏性分析；模型评价；参考文献；附录。Summary Sheet、正式编号和单列AI报告服从适用规则。方法总览放分析末；每个子问包含模型、算法、验证、结果图表和解释边界；结论建议归模型评价。

从大纲建立“题问—主张—证据—图表—章节”清单，先粗图与一句主要发现再精修。方法/框架示意通常全篇1–2张，结果/验证/灵敏性图按证据需要，不设总图数配额。白底、统一字体、蓝/青绿/橙、线型与标记，最终PDF核心图文12pt；输出PDF、SVG、300dpi PNG、代码、数据映射和英文图注。

编程/验证核数、论文负责人核表达、排版核入稿、非作者看完整图及最终PDF。数学冲突回建模负责人，不能在润色时改含义。精简冗余表述而保留必要来源，引用数量本身不代表重复率。

独立新项目可运行四图合成演示：

```powershell
python scripts/figure_demo.py --root . --skill-root "$env:USERPROFILE\.dsh\skills\nature-figure"
python scripts/paper.py --root . build --demo
```

示例含方法总览、结果对照、灵敏性和参数包络，始终标注synthetic。不提供skill-root只执行项目检查，不能声称执行了专项技能。正式骨架用paper.py --root . build；详情见项目paper/README.md。编译通过、内容完整、视觉通过分别记录，不以自动评分替代审美。

## 关口与恢复

H0题意选题、H1模型、H2核心结果边界、H3最终稿来自真实用户确认。H2绑定模型/结果/同代验证，H3绑定确切PDF及消费结果。排版变化复查PDF，不自动恢复或扩大科学批准。Codex作者成果也交非作者验收。

```powershell
python scripts/mcm.py --root . context-pack TASK-ID
python scripts/mcm.py --root . validate --strict
python scripts/mcm.py --root . refresh
python scripts/mcm.py --root . gate H2_RESULTS
python scripts/mcm.py --root . snapshot last-good
python scripts/mcm.py --root . restore last-good
```

命令只检查，不授予批准。当前依赖失效会阻断；无关历史失效成果保留提示。恢复写入独立目录。整改由原审阅者或指定非作者复验，默认最多三轮，仍阻断则提交回退/缩减决策。

AI归档保留可见输入输出、实际模型、PTC及附件清单，排除内部推理和凭据；核对warnings与覆盖，失败可用原生/export补充。实际核验后才登记人工确认，正式披露按适用政策生成。内部评分只排序改进项，不保证O奖。

流程与故障索引见[协作协议](docs/协作协议.md)及diagrams三张架构图。

</details>
