# 记录模板使用说明

这些 JSON 是结构模板，`_template_only=true`，不是真实成果、证据或批准。复制到自己的 `tasks/<task_id>/`，填写真实值并将 `_template_only` 改为 false，再交队长合并。空路径、空哈希、未填写公式/验收不能进入正式运行或关口。

四个必需 registry 的外层均为 `{"format_version":1,"records":[]}`；以下单记录放入对应 records，不要把整个 registry 再嵌一层。成果版本为正整数，从 1 递增；refs 必须保存当时版本和 SHA256。verifier 是具体实例 ID，不能只写角色名或原作者。

| 模板 | 用途与位置 |
|---|---|
| task-card.json | 队长派发任务，合并 tasks registry |
| handoff.json | 子角色→父层交接，保存在任务目录 |
| model-contract.json | 模型→代码的可执行契约，登记为 model 成果 |
| evidence-card.json | 原文、数据和参数依据；资料登记/证据目录 |
| artifact.json | 版本化成果，合并 artifacts registry |
| review-issue.json | 独立问题，合并 issues registry |
| decision.json | 路线/风险/调度等决定，合并 decisions registry |
| human-confirmation.json | 真实人工关口决定，合并 decisions，字段同步 config/gates |
| figure-contract.json | 图表支持主张、数据、脚本和输出 |
| ai-usage.json | 实际 AI 用途与采用记录 |
| scorecard.json | 自拟内部评分，不代表官方分数 |
| verification-report.json | 独立结果复现；由 artifact.verification_report 引用 |
| issue-closure-evidence.json | 非作者关闭问题的实际证据 |
| run-manifest.json | 实际运行命令、配置、数据与输出索引 |

`artifact.status` 与 `approval_state` 是两个字段。`verified` 表示核验层级，真实人工关口批准仍需独立记录。合成演练记录始终 synthetic=true，不能靠修改成 false 或 allow-synthetic 参数进入真实比赛链。

人工确认模板默认 pending，`decision=null`。只有用户真实确认后，队长才填 decision=approve/reject、approved_by/at、用户依据和具体 scope_refs。gate 的 scope_refs 必须与对应 decision 完全一致；不得预填一份“示例用户已批准”。

review-issue.author_agent_id 是被审成果的作者；reported_by 是提出问题的人。closed_by 必须为非作者，verification_evidence 保存实际关闭证据文件及哈希。作者回复不等于关闭。

AI报告还使用 `ai-human-verification.json` 记录真实批量核验依据；`paper-visual-review.json` 是逐页检查模板，核验后保存到 `reviews/paper-visual-review.json`，用于 `paper.py check PDF --release`。模板中的pending/false不得预先改为通过。
