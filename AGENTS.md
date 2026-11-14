# 本仓库的维护约定

本仓库是 MCM A/B/C DSH PTC 预设及项目模板的维护源。
远程：`https://github.com/ncgz202106/mcm-dsh-team`；用户于2026-10-26明确要求公开，当前为公开仓库。
当前目录是唯一源码根；DSH 安装目录是部署副本，不作为另一个维护源。

## 已授权的 GitHub 同步

用户已明确要求“以后改动同步 GitHub”。今后完成本仓库的修改后：

1. 查看 Git 状态、当前分支和远程更新，保留用户及其他 Agent 的工作。
2. 运行与改动相应的构建、检查或测试；证据中区分实际执行与历史报告。
3. 检查待提交清单，排除凭据、原始会话、内部推理、本机 profile、安装备份和真实比赛项目。
4. 只提交本次已核验的相关改动，以清楚的提交说明记录原因和验证。
5. 正常推送当前项目的对应分支，读回远程提交并核对 SHA；无需为已授权的普通同步再次询问。
6. 遇到认证、冲突、推送失败或未完成检查时如实报告，保留本地成果，不声称已同步。

不强制推送，不重写既有历史，未经用户新的明确授权不改仓库可见性或权限，不推送无关项目。
这些约定适用于协作中由 Agent 完成的修改；不安装后台文件监视器，也不自动提交用户尚在编辑的内容。

## 预设与模板维护

- 保留原角色 ID 兼容、深度和单写入者约束；用户暂停与人工关口继续有效。
- 维护此代码仓库不等于恢复 `E:\meisai` 的原演练，不自动更新活跃 DSH Host。
- `project-template/` 和 `rehearsal-v2/` 内的 AGENTS.md 是比赛项目的交付内容；维护任务不因此启动比赛任务。
- 图表和论文仍遵循用户结构、真实证据、最终尺寸、独立审阅与逐页视觉检查。
- 修改提示词/路由后用 `node bundle/src/build.mjs` 生成有效配置，再执行 `--check` 和相关测试。
- 当前维护版本为0.2.1。默认图表样式只改 `bundle/src/figure-style.json`，用构建器 `--sync-project-style` 同步模板并检查；MCM专项引用只在 `skill-overlays/` 维护。使用 `python tools/verify-v021.py --run-tests` 检查当前源码，不把audit根的0.2.0旧报告当作新版本通过。
- 软件回归入口：`python -m unittest discover -s project-template/tests -q` 与 `node --test bundle/tests/*.test.mjs`。
- 原生运行时、桌面模型和视觉检查有不同范围；未实际复验时明确缺口。
- 冻结的验收报告、原始制品及其哈希保留历史含义，不能改数字伪造新版本通过；新候选另留相应证据。
- 图表/PDF/架构图及过滤后的 audit 是仓库内容，不能用 blanket build/、*.pdf、*.png 忽略规则破坏证据链。

使用与同步入口见 README.md 和 docs/GitHub同步.md。

## 定向模块路径

- `bundle/prompts/` 与 `bundle/src/skill-routing.mjs`：角色职责、专项Skill路由；`node bundle/src/build.mjs`生成有效预设。
- `skill-overlays/`：五项Nature工具的MCM适配分支；`tools/skill-overlays.py`备份、应用及回滚，不覆盖通用主Skill。
- `skill-overlays/nature-figure/references/mcm-visual-recipes.md`与`scripts/mcm-gallery.py`：按需选图和六组合成布局；配套style资产由构建器`--sync-project-style`从bundle唯一源同步。支持资源须列入overlay manifest的resources，禁止覆盖通用上游脚本。
- `project-template/scripts/figure_check.py`：图表文件、尺寸和来源核对；`visual_range.py`检查最终坐标是否隐藏源点或区间。
- `project-template/tests/`、`bundle/tests/`：Python和Node回归；`docs/科研图表与论文经验.md`记录可迁移经验。
- `adapters/codex/build.mjs`：从共享角色和资源生成 Codex 项目配置及入口，运行 `node adapters/codex/build.mjs --check` 核对生成文件。
- `project-template/resources/mcm-skills/`：DSH 与 Codex 共用的写作和图表文字参考。公开图表索引位于 `adapters/codex/skill/references/chart-gallery.html`，原论文图像保存在本机。
- `tools/codex-project.py`、`tools/install-codex-skill.py`：新项目、兼容预览、入口安装及回滚。测试在 `adapters/codex/tests/`。
- `project-template/scripts/codex_control.py`：任务批次、收件、快照和恢复诊断。`section_visuals.py`核对逐小节图表覆盖。
- `project-template/scripts/paper_finish.py`：终稿候选检查、编译渲染与受限尺寸修复，`paper.py finish`转发；`paper/styles/mcm-layout.tex`维护新项目版式。
- `project-template/resources/mcm-skills/presentation-lessons.md`：优秀论文的实际读页与论证迁移；`skill-overlays/nature-figure/scripts/mcm-advanced.py`提供有二维配套的三维配方。
- `skill-overlays/nature-figure/references/mcm-scientific-grammar.md`：机制/框架/反馈、符号情景、计数和组成的视觉语法；`mcm-schematics.py`和`mcm-evidence-panels.py`为原创合成起点，审阅记录在对应`docs/figure-recipes/`和日期audit。

图表教学库和图型建议服务具体主张，不机械增加图数或套用模板。正文、参考文献、AI披露及附录分别报告；官方页数预算按项目规则核对。更新源码与本地Skill不等于已在DSH新会话运行验收。
