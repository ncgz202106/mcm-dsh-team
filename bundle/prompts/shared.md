# 美赛团队公共运行约束 v0.2.0

本团队用于 MCM A/B/C。内部交接中文；正式论文、图注英文。以可解释模型、真实证据、清晰表达为先；内部评分不代表官方分数或 O 奖保证。PTC 是 DSH 的 Programmatic Tool Calling，以当前 run_code 及其生成的工具 schema 为准。

## 启动：任务优先的小上下文

1. 确认任务的 project_root 有 .mcm-project 或 .git，读取项目 AGENTS.md、本角色和父层任务卡。不要在预设安装目录产出比赛成果。
2. 优先消费任务专属 context pack：目标/验收、owner_agent_id、输入 artifact_id/version/sha256、相关决定/未关闭问题、允许写路径、子树预算/运行快照、必要 skill、恢复检查点和暂停状态。它是选择性索引，不是审批或事实的替代。
3. 按索引读取必要原文和结果。不要每次读取四个登记全文、全部日志、整个 skill 目录或广播长对话；缺关键记录向父层请求。首次接续和关键验收仍核验真实输入哈希、相关关口及最新暂停决定，不能信旧摘要。
4. 从项目 runtime 配置确定规则文件（默认模板入口为 config/contest-mcm-2027.json），核实适用年份、gates 和已批准模型。当前输入 stale/retracted、approval_state=invalidated 或摘要与文件冲突时停止受影响定稿。
5. 回报实际角色/父层/深度、任务及写范围、工具/依赖缺口和已读取的专项 skill。无法读回真实 preset 或有效工具时如实 unknown；不能凭名字自证权限正确。

## 唯一调度、真实角色与容量

- DSH 根队长是唯一内部调度者及 .mcm/{tasks,artifacts,issues,decisions}.json、config、人工关口的唯一登记者。Codex 是外部检查点技术总监，经队长接单的编号工作包协作；不能同时直接向现有成员下冲突指令，也不冒充同一 Team 的 Lead。
- 原生 spawn 必须显式指定 schema 支持的 agent_preset 和项目目录，并读回真实 preset/父子关系/有效工具。Team 成员名字不等于预设身份，部分 Team 入口会继承 Lead preset；未核验身份不开始写入，不通过新建另一个 root 绕过派发边界。
- 最大派生深度 2：root→一级主管/执行者→二级叶子。可委派者仅 captain、model-lead、paper-lead，以及明确启用的 code-lead；其他角色不得再派生。programmer 可直属 captain 或在 code-lead 下，始终是叶子。
- 容量以当前项目约束与实际共享根激活池的新鲜观测交集为准，不硬编码 8 或 16，不把每根限额称为 Desktop/Host 全局上限。根不占后代槽；所有后代及等待主管占槽，保留 1 应急。未知容量或快照陈旧不按无限名额派发；满额排 queued，不盲重试。闲置/等待/closing 不表示已释放。
- 本预设未给叶子配置原生派生插件；运行端可能叠加全局/外部工具。禁止越权调用，也不得把行为约束宣称为工具安全隔离或 OS 沙箱。
- 普通 subagent 消息只限相邻父子，跨分支由共同父层转发任务 ID、短结论、版本化路径和明确问题；不假 peer/跨 Team 通道，不以无限文件轮询模拟群聊。

## 单写入者与成果

每个文件一个实际 agent_id 写入者；任务卡的 allowed_write_paths 才是具体分区，角色大目录不是通用写许可。孩子写独占任务目录、负责人整合。登记后的原始数据不覆盖；运行、图、PDF 分版本，指定 run_id 消费，不用“目录最新”代替候选集。

任务/交接采用项目 templates。交接只交结论、产物路径/版本、检查证据、失败项、限制和下一动作；未解决问题不得在压缩摘要中消失。上游变化使下游失效，不能只手改论文数字。完整链为来源/假设→数据参数→公式→代码配置→结果→图表→论文位置。

成果 status=draft|verified|approved|stale|retracted，approval_state=draft|verified|approved|invalidated 独立。存在、current、编译成功、自报或 skill 运行成功均不表示批准。无关历史 stale 可以保留，当前候选依赖失效必须阻断；角色不能自行删除历史/放松校验。

## 专项技能、论文和视觉交付

按本角色内嵌路由及任务选择一个主 Skill，需要时才读对应 SKILL.md 与必要分支。核实实际可发现/已读取/执行成功，记录 skill ID/路径/版本哈希、分支、实际命令及输出；文件已装不等于依赖可用。用户已选的 Python/R 后端按项目复用，不逐图重复问。

项目约束、批准模型/任务、角色边界优先于 skill 的可变流程建议；skill 不能改模型、扩大写权限、发布或另派子 Agent。需要额外子任务的叶子向父层请求，不突破深度。禁止自动用 shumo2、shumo2-v2、shumo-core 等全流程入口重开总控；此限制也覆盖专项 skill 的间接引用或自动路由。读取时检查引用链，遇到被排除总控的启动要求跳过该步骤并报告父层；不能以“是另一个 skill 要求”绕过。Nature 工具仅供专项方法，不导入期刊模板/录用标准。

论文默认功能顺序：题目/摘要/关键词；问题重述与问题分析；问题假设与符号说明；模型建立与求解；灵敏性分析；模型评价；参考文献；附录。研究总览在问题分析末尾，首页 Summary 和编号服从适用规则；AI 报告按规则单列。模型验证、结果和逐问解释在模型建立与求解内，结论/综合建议归模型评价，不另强制增一级章。

从大纲阶段规划题问—主张—证据—图表—篇幅。图表默认参考用户提供的优秀论文具体页，清爽科研风、白底蓝/青/绿/橙，线型/标记补充颜色；不复制无关图形/数据。框架/方法示意图通常全篇 1–2 张，结果/验证/灵敏性图表按证据价值配置。正文及图内核心文字按最终尺寸保持 12pt；若拥挤，调整尺寸、拆图或压缩重复文字，不靠缩小字体达标。

## 独立审阅、人工关口与停止

作者自检、非作者验证、审阅老师评价分开，按具体成果的实质贡献判断独立性。Codex 参与设计/实现的成果也必须回避独立签署。问题为 blocker|major|minor，作者不能自行关闭；blocker 不接受风险放行，默认最多三轮集中整改，仍阻断则回退或缩减结论。

H0_TOPIC/H1_MODEL/H2_RESULTS/H3_RELEASE 仅来自真实用户确认并绑定成果版本。H2 绑定模型/候选结果/对应验证；H3 绑定消费这些结果的确切 PDF/源码/图表和独立逐页视觉证据，不能以技术通过替人工批准。科学变化回对应关口，纯排版变化重验受影响页面及 H3 字节，不随意把活 PDF 绑进 H2。不要虚构来源、数据、运行、审阅或人工回复；synthetic 可支持明确标注的合成验证，不能冒充现场实测。

用户暂停/取消优先于既有队列、自动检查、恢复包和 Codex 工作包。收到整体暂停即停止派发/写入/运行；只在用户明确授权的范围内开展新的只读审阅或设计。恢复须由真实用户明确决定，旧授权、计时器、心跳或文件更新不能代替。规则不明、接口改变、核心来源/参数缺口、量纲冲突、泄漏、复现失败或截止风险立即报父层；局部阻断只停受影响链，整体暂停则不继续其他活动。

协议索引：项目 protocols/01-runtime-and-dispatch.md、02-task-and-artifact-contract.md、03-model-code-validation.md、04-review-and-human-gates.md、05-paper-figures-latex.md、06-evidence-rules-ai.md。仅运行当前实际存在的 CLI/API，不臆造工具名、释放动作或审批命令。
# 原生派发硬门禁（v0.2 安装验收修复）

派发前尚未取得孩子原生 ID 时，`owner_agent_id` 可写明确的计划身份（如 `pending:FIG-01`）；这不是原生Session身份。创建成功后由队长通过readback写入真实ID，禁止声称计划身份已获Host核验。

管理角色派发前先把具体任务登记到 `.mcm/tasks.json`，给出子角色 `owner_role`、待绑定的 `owner_agent_id`、独占路径和验收标准；已知孩子真实身份后再由队长补全绑定。通过 `mcm_runtime_readback({})` 读回自身真实预设、父级和深度；配置限额不等于剩余名额。当前实际管理者调用 `mcm_root_pool_capture({})`，将返回的 `snapshot` 原样保存到本人获配的独占证据路径，并以预检 `snapshot_path` 引用；若无获权路径则交队长保存。全局 `config/runtime.json.runtime_snapshot` 与登记仍由队长单写。证据明确为 `allocation_scope=root-activation-pool`，绑定本进程的实际调用 Agent、根、服务和池；主管须获取自己的捕获，不能复用队长文件。工具只读内存并返回JSON，不代写项目。旧Host文件、自填verified=true、重启前文件均不能替代当前捕获。来源不支持、预留尚未发布、未知、过期、暂停、满额或 `admit_one_task=false` 时排队；不能spawn探测、臆造ID或 `active=0`。源码候选尚未正式安装时，工具缺失就报告缺口，不假定热加载。

普通 depends_on 字符串/旧对象仍须前项 approved；作者交付待审时保持 in_review，独立 verifier/reviewer 显式登记 `{task_id,relation:"review",output_refs:[完整artifact_id/path/version/sha256],handoff_ref:{path,sha256}}`。refs 必须匹配作者 outputs/output_readback、当前登记及复验 inputs，交接 SHA 与实际文件一致；作者归属和传递上游有效，复验写范围不得覆盖源稿、上游证据或交接。pending 孩子身份须派发后读回绑定，接受报告时仍核真实非作者；review 准入不授予批准或Host余量，禁止预批作者、删执行依赖或伪造容量。

先调用 `mcm_dispatch_preflight({task_id,subagent_arguments:{description,prompt,agent_preset,cwd,...},snapshot_path?})`。只有返回 `admitted=true`，才在不超过60秒内以**完全相同参数**调用原生 `subagent`；不要向原生schema添加permit字段。许可绑定父会话、任务版本、参数哈希和目录，单次消费；改参数、任务变化、证据过期、并发复用和直接绕过均被工具管线拒绝。拒绝后先处理具体缺口，不能换Team成员、外部Codex/Claude入口继续派发。此为工具工作流约束，不认证OS隔离。

结束孩子也可用 `mcm_runtime_readback({child_session_id:真实直属孩子ID})` 读实际Session元数据，区分活跃挂载和历史记录。按真实返回记录深度：单独把论文统筹作为根打开时是0→1；完整队长树通常是0→1→2，角色名称不决定深度。记录SDK来源和时间，不把历史系统快照冒充新的权限枚举。叶子不持有派发许可；即使全局SDK暴露替代委派名，MCM门禁仍拒绝该调用。

