# 本地演练与可验证交接

这是多 agent 预设的轻量本地配套工具，不是另建 agent 平台。它记录任务、成果、审阅问题、人工决策，检查文件摘要和上下游版本；不会调用 DSH、创建会话、读取凭据或替用户批准和提交论文。

## 运行环境

默认 Python 3.12、独立 `.venv`。若 Windows 的 `py` 启动器已登记 3.12，可在项目根运行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/mcm.py --root . doctor
```

也可使用交付包的 setup 脚本选择本机实际存在的 Python 3.12；不要为兼容而复制他人的绝对用户路径。CLI 与 unittest 仅用标准库；图表需要 matplotlib；PDF 检查需要 pypdf。LaTeX 工具链由 `scripts/paper.py` 独立检查。项目开发时已在本机 Python 3.14.7 下测试 CLI 与演练；这不等于已验证所有系统的 Python/TeX 安装。

所有命令默认以 `scripts/mcm.py` 上一级为项目根；建议显式写 `--root`。`--project` 为兼容别名。命令输出 JSON，检查失败返回退出码 2。`.mcm-project/` 是可移动项目标记。

## 合成演练

示例仅用于演练交接和验证，不代表任何真实赛题或实测数据。合成输入位于 `example/synthetic_input.json`。

模型：最小化 `x²+2y²`，约束 `x+y=T`，`x,y≥0`。取 `T=12`，解析解 `x=8,y=4`，成本 96；均分基线成本 108，改善 11.111111%。灵敏度场景 `T=8,…,16`，最优成本 `2T²/3`。所有量都是合成单位，没有经验样本、置信区间或统计显著性。

```powershell
.\.venv\Scripts\python.exe scripts/mcm.py --root . demo
.\.venv\Scripts\python.exe scripts/mcm.py --root . validate --strict --allow-synthetic
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

如果包内已经附带演练输出，第一条会拒绝覆盖。检查后可显式使用 `demo --force`，该开关仅重建固定的合成演练文件。真实项目请从干净模板副本开始；demo 遇到非演练成果登记会停止。

流水线依次运行解析求解、独立网格搜索和有限差分验证、图表导出、LaTeX 数值及表格导出、成果登记。独立验证脚本不导入求解器，重新计算约束、目标、基线与节省比例，并通过 12,001 点网格和数值梯度核查最优性；这属于该小型合成问题的独立数值复现。

| 交付 | 路径 |
|---|---|
| 求解结果 | `results/demo/results.json` |
| 独立验证报告 | `results/demo/verification.json` |
| PDF / 300 DPI PNG / SVG | `figures/demo_tradeoff.pdf` / `.png` / `.svg` |
| 数值宏 | `paper/generated/results.tex` |
| 三线表 | `paper/generated/demo_table.tex` |

数值宏为 `\DemoDemand`、`\DemoX`、`\DemoY`、`\DemoCost`、`\DemoBaselineCost`、`\DemoSavingPct`、`\DemoMaxVerificationError`、`\DemoGridGap`。论文应引用生成宏和表，不手抄数字。图为确定性需求趋势和资源分配比较；颜色搭配线型/点形，分配柱从零开始，不添加虚构误差棒。版面终审仍需查看实际导出的图与最终 PDF。

demo 的成果全为 `synthetic:true`、`approval_state:verified`，任务为 `in_review`；**不会生成任何人工批准**。`--allow-synthetic` 只允许检查演练证据，不会将其变为真实赛题成果。所有人工 gate 保持 pending，正式提交仍由人执行。

## CLI 与记录约定

四个必需 registry 位于 `.mcm/{tasks,artifacts,issues,decisions}.json`，统一为：

```json
{"format_version": 1, "records": []}
```

角色使用 `templates/` 的单记录模板交付提案；队长读取提案和证据后，通过 `import` 合并至 registry。`status` 表示生命周期，独立 `approval_state` 表示 `draft|verified|approved|invalidated`。文件存在、任务结束、`verification_status:passed` 都不自动等于人已批准。

```powershell
python scripts/mcm.py --root . import artifacts reviews/artifact-proposal.json
python scripts/mcm.py --root . import tasks reviews/task-update.json --replace
python scripts/mcm.py --root . validate
python scripts/mcm.py --root . gate H2_RESULTS
```

人工 gate 为 `H0_TOPIC`、`H1_MODEL`、`H2_RESULTS`、`H3_RELEASE`；也接受 H0–H3 短名。`gate` 只检查，不修改批准状态。人工决定记录必须含 `decision_type:human_gate`、`decision:approve`，并与 gate 的 `decision_id` 和 `scope_refs` 对应；scope 中每项绑定 `artifact_id`、`version`、`sha256`，已批准成果的 `approval_state` 必须为 approved。获准前应从真实的人类回复记录 `approved_by`、`approved_at`，不得由 agent 填造。检查围绕所选 scope 及其上游证据展开，不会把其他候选草案一并提升为批准。

严格检查拒绝：失效的输入版本或摘要、未通过的独立验证、需要复现但未复现的结果、需核验但未核验的引用、作者自己验证自己、未关闭 blocker，以及将合成成果混入真实 gate。结果类成果还必须给出 `verification_report:{path,sha256}`；报告的 `status:passed`、`result_sha256`、`reproduction_passed:true` 和独立 `verifier_agent_id` 都必须匹配。此工具检查证据结构与一致性，不能代替建模专业判断、文献原文核验或人工身份认证。

### 输入变化和失效

每份 artifact 的 `inputs` 为 `[{artifact_id,version,sha256}]`；文件 `sha256` 使用 SHA-256。依赖图必须无环。

```powershell
python scripts/mcm.py --root . refresh MODEL_Q1 --reason "参数来源更新"
python scripts/mcm.py --root . invalidate RESULT_Q1 --reason "发现目标函数实现错误"
```

`refresh` 比较实际文件摘要；发生变化时递增该成果版本，重置验证和批准，并递归将下游结果、图表、论文标为 stale/invalidated；涉及的人工 gate 同时 invalidated。`invalidate` 无需改动原文件即可撤销当前成果及下游。修复者必须重新生成、复核并登记完整依赖，不能只改状态绕过验证。

### 写入分区与审阅关闭

`config/runtime.json` 给出分区所有者。worker 将候选文件写到自己的版本化分区；`write-output` 使用独占创建，拒绝覆盖现有文件、跨分区写入、`..` 越界及写入 `data/raw`。共享 registry 仅由 captain 合并，使用 `.mcm/write.lock` 防止并行写入。崩溃留下锁时，先确认记录的进程已停止，再由队长恢复；不要自动删除仍在使用的锁。角色名和文件锁是协作约束，不是操作系统权限隔离。

```powershell
python scripts/mcm.py --root . write-output tasks/WRITE1/draft/q1-v2.tex reviews/q1-proposal.tex --actor mcm-writer --task-id WRITE1 --agent-id ACTUAL_WRITER_ID
python scripts/mcm.py --root . close-issue ISSUE-001 --verifier reviewer-2 --evidence reviews/ISSUE-001-verification.json
```

问题先转为 `fixed_pending_review`，再由非受审成果作者的验证者关闭。验证文件须含匹配的 `issue_id`、`verifier_agent_id`、`status:passed`；工具保存并复核其摘要。blocker 不允许用 accepted_risk 关闭。

## 容量与 DSH 运行时

常规 7 个子 agent 槽位，加 1 个仅供复现、技术审计或紧急修复的预留槽位；队长根会话不算槽位，等待中的主管仍占槽位。角色是职责，不等于全部同时常驻；主管结束已完成工作、释放槽位后再开下阶段子 agent。

从真实 DSH `listRuntime` 返回结果人工归一化后，保存本地快照：

```json
{"records":[
  {"agent_id":"captain-runtime-id","role":"captain","state":"running","is_root":true},
  {"agent_id":"model-runtime-id","role":"model_lead","state":"waiting","is_root":false}
]}
```

```powershell
python scripts/mcm.py --root . runtime --snapshot reviews/runtime-snapshot.json
python scripts/mcm.py --root . runtime --snapshot reviews/runtime-snapshot.json --reserve-task
```

状态支持 running/waiting/starting/paused/completed/cancelled/failed；前四种占槽位。只有快照中明确 `is_root:true` 的根记录被排除。没有快照时工具只显示配置容量，不声称 DSH 实际空闲。该命令不调用 listRuntime、不派发任务；真实派发仍使用 DSH 已验证的原生工具与预设。

## 快照、故障恢复和截止时间

```powershell
python scripts/mcm.py --root . snapshot before-paper-integration
python scripts/mcm.py --root . restore last-good
```

快照创建前进行完整性检查，保存配置、registry、代码和产物的清单及摘要；不会将“完整性通过”说成“科学结论获准”。快照标签不可覆盖，`.mcm/last-good.json` 记录最近成功的完整性检查点。原始 data/raw 只登记摘要，不在快照中复制大文件；请在赛前另行保留不可变原始数据备份。

恢复先核验快照摘要和原始数据摘要，只写入 `.mcm/restored/<新目录>/`，不覆盖正在使用的项目或原始数据；向恢复目录复制经核验的原始数据并设为只读。原始数据已变化时恢复停止，要求先找回不可变原始输入。恢复后在新目录运行 validate，明确切换工作区；不会静默覆盖当前会话。`restore --destination` 只能指向 `.mcm/restored/` 内尚不存在的新子目录。

2027 配置已于 2026-10-24 核对，保留官方来源；北京时间 2027-01-29 06:00 开赛，2027-02-02 09:00 停止全部修改，10:00 提交截止。99 小时工作窗口与最后 1 小时提交窗口必须区分。CLI 不代替赛时调度器：队长及所有工作角色必须按规则停止修改，提交窗口只能上传已冻结 PDF。正式赛前重新核对官方规则和具体题面，不能把该预设中的年份默认视为永久有效。

## 故障注入覆盖

`tests/test_mcm.py` 使用标准 unittest 和临时目录：测试旧摘要递归失效、输入版本漂移、真正篡改数值后的独立复核失败、未核验引用、复现失败、blocker 独立关闭、证据摘要、并行写锁、分区写入不覆盖、越界/原始数据保护、循环依赖、7+1 容量、合成证据不得批准真实项目，以及快照恢复和篡改检测。所有测试中的批准都是临时的显式合成样例，真实项目的人工决定保持空白。
