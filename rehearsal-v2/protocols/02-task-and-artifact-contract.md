# 02 任务、版本化成果与恢复

## 任务契约

每次派发实例化 `templates/task-card.json`。至少包括目标、负责角色/实例、父任务、输入 refs、依赖任务、输出路径、独占写入范围、验收条件、优先级、阶段、截止/预算、允许孩子、人工关口和升级条件。没有输出路径或验收条件的“大概做一下”不得视为正式任务。

任务状态为 `queued → running → in_review → approved`；可转 `rework|blocked|cancelled`。approved 表示任务验收通过，不能自动把其中所有成果或人工关口批准。普通局部修改用局部任务，不为改一句话重跑整套流程。

交接必须列实际输出、实际检查和未完成项；不要只给长篇推理。父层检查产物和证据后，队长写全局任务状态。子角色提交 handoff，不直接并发修改全局登记。

## 全局登记与单写入者

四个必需登记 `.mcm/tasks.json`、`artifacts.json`、`issues.json`、`decisions.json` 均为 `{"format_version":1,"records":[]}`，队长唯一写入。资料卡和 AI 用途可另登记在 `.mcm/evidence.json`、`.mcm/ai-usage.json`，也经队长合并。模板是未实例化结构，不能直接导入为真实证据或批准成果。

| 内容 | 默认唯一负责人 | 其他人如何贡献 |
|---|---|---|
| config、四登记、人工批准 | 队长 | 提交任务交接/记录建议 |
| 模型契约、统一符号、模型决定 | 建模负责人 | modeler 写独占候选目录 |
| 来源、原始文件登记、独占清洗输出 | 检索 | 请求数据/参数，不覆盖原件 |
| 求解代码、配置、运行结果 | 编程 | 提 issue 或最小复现 |
| 独立验证证据 | 验证复现 | 作者提供说明，不替验证人签字 |
| 主稿、正式章节和论文引用库 | 论文负责人 | writer 提草稿，typesetter 提补丁 |
| 图脚本和图输出 | 图表角色 | 编程核数字，论文核表达 |
| 样式、构建输出和视觉报告 | 排版角色 | 主稿修改由论文负责人整合 |
| 独立审阅报告 | 审阅老师 | 作者回应，非作者关闭问题 |

每次任务可细化目录所有权，但不能出现两人同时改一个文件。不同角色共享目录时必须分配不同子路径。

## 成果状态与引用

成果记录使用 `templates/artifact.json`，输入统一为 `inputs:[{artifact_id,path,version,sha256}]（旧refs可省path，新建引用应成套写入）`；版本是从 1 递增的正整数。路径使用项目内相对路径，不把机器绝对路径写进可移植交付；禁止 `..` 越界。关键最终成果必须存在、哈希已计算且与文件相符。

- 生命周期 `status=draft|verified|approved|stale|retracted`。
- 独立批准 `approval_state=draft|verified|approved|invalidated`。
- 验证 `verification_status=pending|passed|failed`；并记录 verified_by、reproduced、citations_verified、synthetic。

`verified_by` 为本次独立核验者的实例 ID 字符串，默认 null；多人参与另记 reviewer_ids。结果成果 `kind=result` 还须绑定 `verification_report:{path,sha256}`，报告对应当前 result_sha256、status=passed、reproduction_passed=true，且 verifier_agent_id 与 verified_by 相同、与 author_agent_id 不同。模板中的待核验值不能用于放行。

`status=current`、文件存在、作者说完成、工具返回成功均不是批准。最终成果要同时满足批准、输入有效、相关关口和验收。不能使用旧版本批准来覆盖新内容。

已登记输入发生字节/版本改变，直接及传递下游置 `status=stale`、`approval_state=invalidated`，并重审相关 gate scope。失败/过时结果不删除，保留审计痕迹，正式清单仅指向当前批准版本。纯版式改变可能只需重新 PDF 视觉核查；改变数字、模型或结论必须回上游。

## 最小恢复机制

每个运行用独立 run_id，图用 figure_id/version，PDF 用独立构建输出。维护最近完整、可编译且数字一致的快照；snapshot 只是保存，不替代批准。

restore 默认恢复到 `.mcm/restored/<snapshot>/` 新目录，先检查，再选择性接回；不覆盖 `data/raw` 或未审阅当前成果。不得在失败后把旧结果复制到新运行冒充成功。新任务接续必须读取最新登记、未关闭问题、输入版本和最后交接。

检查点归档 tool 结果若 partial，列缺失项并保留 `pending` 人工核验。只有实际确认的完整交付可以进入最近可用清单，不能因归档命令退出 0 就认为科学链条通过。

## 任务上下文与交接读回

任务可选specialty、dispatch_parent_role、required_skills、decision_refs、skill_readback、output_readback，旧任务缺字段仍可读取。required_skills列名称、SKILL.md来源和用途；skill_readback记录实际读到的版本/摘要、使用点和时间，不推断为已读。handoff output_readback列每份交付path/SHA/size/读取者/检查结果；父层收到后再次读回，再由队长合并登记。

context-pack TASK_ID只输出目标任务与输入依赖闭包、相关决定摘要、open issues、技能、验收、写范围和暂停状态，绝不输出全部会话/推理。正文通过路径按需读取。过期成套引用、缺依赖、无效写范围或item预算截断会使ready_to_start=false，先修任务或拆分。generated_at与导入的registry_recorded_at由工具UTC时钟生成，作者自报时间保留但不作真实事件排序依据。

历史stale/retracted成果保留，若不在当前候选依赖闭包只记warning；当前链引用它仍阻断。验证按当前依赖闭包，不要求退役旧报告为了形式重新通过。显式选择某历史成果验收时，它本身成为当前检查对象，必须失败。

限时交接包含from/to实例、源文件path/SHA、permission_granted、permission_expires_at和reclaimed_at。实际接收者和源SHA需匹配；到期、回收或源变化立即停止写入。旧true grant不能盖过新回收；读回不是权限升级。
