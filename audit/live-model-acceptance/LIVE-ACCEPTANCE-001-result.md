# LIVE-ACCEPTANCE-001 — 结果报告（v0.2.0 安装后隔离验收 · synthetic）

- 报告生成：2026-10-25T23:03:51+08:00
- 任务卡：`audit/LIVE-ACCEPTANCE-001.md`（唯一项目根 = 唯一 cwd）
- 性质：**合成软件演练（synthetic=true）**，不是比赛科学工作，不授予也不代签任何人工关口
- 结论：**passed_with_documented_gaps** — installed / read / executed / 机械验收通过；视觉 pending；Host 容量准入与 preset 机读回读两项过程证据不成立（见 GAP-01/02）
- `human_gates_modified = false` · `original_rehearsal_resumed = false`

---

## 1. 会话、角色、父子（只用可见公开信息）

| 项 | 父级（本会话） | 子实例 |
|---|---|---|
| 标识 | Team Lead target = `lead`，list_agents role = `lead`，model = `deepseek-flash` | subagentId = `84c73a8b-23e1-4b59-a667-02273e066615`（spawn 返回 `kind=activation`） |
| 角色 | 自述 `mcm-paper-lead`（依据：注入的角色说明 + 运行时上下文，**无 Host 机读回读**） | 声明 `agent_preset=mcm-figure`（工具 schema 可选值 + 被 Host 接受 + 子自述） |
| 深度 | 1 | 2（自述） |
| 父级可证实性 | — | 子自述 parent = `session-5cb9f2f7-…`，父级无法确认 |

**可见事实：** spawn 前后 `list_agents` 都只有 `lead` 一项 —— 原生 `subagent` 子实例不进入 Team 成员列表，Team 口径下没有新增成员。

**回读边界（重要）：** 没有工具能读回子实例的 effective preset 字符串或父子图。子实例结束后父级尝试 `send_message` 其 subagentId 索取角色原文，被拒（`active teammate not found`）——原生 subagent 是一次性激活，事后无补充回读通道。故"真实角色回读"只达到 **schema 接受 + 自述** 两级。

## 2. 容量与准入（未满足，如实记录）

`python scripts/mcm.py runtime`（无快照）实际输出关键字段：

```json
{"capacity_known": false, "host_capacity_verified": false, "host_max_active_descendants": null,
 "effective_total": null, "snapshot_fresh": false, "admit_one_task": false, "user_paused": false}
```

- 规划默认 7 常态 + 1 应急、`root_counts_as_slot=false`、`max_nested_depth=2`（`config/runtime.json`）。
- 实测：spawn 前活跃后代 0 → 申请 1 → 成功 1，未动用应急槽。
- **准入不成立：** 无新鲜快照、无 Host 容量查询接口，`host_capacity_verification_required` 未满足。**未伪造任何 host_capacity 快照。**
- 仍执行 1 次 spawn 的理由与披露见 `process_deviations/DEV-01`：任务卡要求这唯一一次显式 preset spawn，0 既有后代 + 仅 1 个孩子不可能超额（超额时 Host 拒绝而非超发），按有界容量探针处理，不宣称容量已核实。

## 3. 技能四态（nature-figure 2.8.0）

| 状态 | 结论 | 证据 |
|---|---|---|
| installed | **verified** | `SKILL.md` 12367 B sha256 `5aefe708…88ffc4`；manifest `version: 2.8.0`；三个审计脚本齐全（父级独立复核哈希） |
| read | **verified_partial** | 真读 6 份：SKILL.md / manifest.yaml / static/core/contract.md / static/fragments/backend/python.md（全文），static/core/stance.md（前 ~2.6KB），references/qa-contract.md（**仅目录**） |
| executed | **verified** | `figure_demo.py` exit 0，3.794 s；py 3.14.7 / mpl 3.10.9 / PyMuPDF 1.27.2.3；技能内 subprocess 审计 12 次（validate_figure、audit_pdf_text --min-pt 12、audit_figure_collisions 各 ×4）全部 exit 0 |
| acceptance | 机械 **passed** / 视觉 **pending** | 见下节 |

**读 ≠ 执行**：读 SKILL.md 不计为执行；只有真实 subprocess 退出码才记 executed。未加载任何被排除总控（shumo2 / shumo2-v2 / shumo-core / askill / askill-v2 / math-modeling / mathematical-modeling / paper-spine），含间接调用。

## 4. 父级独立核验（不采信自述）

1. `child-report.json` 28 779 B，重算 sha256 = `5718e26f…41d2`，与自述一致；21 顶层键、40 artifacts、4 figures 可解析。
2. **40 个产物逐一重算哈希与字节 → 40/40 完全一致，0 缺失，0 未申报多出。**
3. 4 份 contract 内部哈希全核（data_inputs / outputs / script_path / qa_readback / numeric_verification_ref / skill_executed.output_refs）→ 每份 `issues=NONE`。
4. 语义约束：`synthetic=true`、`status=draft`、无 `approval_state`、`visual_status=pending`、`qa_readback.visual_reviewed=false`、`minimum_final_glyph_pt=12`、`size_mm=165.1×101.6` → 4/4 通过。
5. **父级独立重跑** `figure_check.py` ×4 → exit 0、`ok=true`、`errors=[]`。
6. 告警复核：全部日志共 **12 条 WARN、0 条 FAIL**（每图 3 条：EXPORT-RASTER 无 TIFF / RASTER-DPI 300 未达技能默认 600 / FINAL-WIDTH 未检出静态最终宽度），与子自述的 3 类一致。
7. 数值：Euler max|err| = `0.01920100107144218`，RK4 = `3.3324105608301124e-07`（脚本守卫 rk4<1e-5 且 rk4<euler 成立）。
8. **父级看图抽查** `comparison.png`（1950×1200）：白底；Analytical 蓝实线 / Euler 橙虚线（略低于解析解）/ RK4 绿点线（贴合解析解）；轴标签含单位说明；图例无遮挡；标题标注 synthetic。与契约主张一致 —— 但**只做了一次抽查，不构成独立视觉审阅**。
9. 受保护文件 20 个 spawn 前后 sha256 逐项比对 → **0 changed**（含 `config/gates.json`、`config/figure-style.json`、`scripts/figure_demo.py`、`paper/main.tex`、`.mcm` 四登记）。
10. 写入越界：新增 42 文件 = `figures/figure-demo/`(40) + `audit/live-figure/`(2)，**允许范围外新增 = 0**。
11. 四 gate 全部 `pending`，字节未变。

## 5. 产物（`figures/figure-demo/`，40 文件）

四图 `method`(示意) / `comparison` / `sensitivity` / `uncertainty`，各含 `.pdf .svg .png`、`.alignment.json`、`.mechanical.json`、`.contract.json` 与三份审计日志；另有 `decay-results.csv`（唯一数据输入，合成计算输出）、`analytic-check.json`、`numbers.tex`、`demo-manifest.json`。

- comparison 契约：6952 B，sha256 `ad66e415cda3538fcfbbb85c2f4c75868328918f35ce085f4b7218410dcbf513`
- comparison.pdf：13663 B，`545ee72a…e5c9`；comparison.png：133731 B，`e01806e5…a77b`
- 数据输入 `decay-results.csv` `5003a103…5627`；解析检查 `af497c2f…4aca`；manifest `9e6e2698…0a31`
- 子报告：`audit/live-figure/child-report.json`（28 779 B，`5718e26f…41d2`）

## 6. 缺口与偏差（不美化）

| ID | 级别 | 内容 |
|---|---|---|
| GAP-01 | major | Host 容量无法核实，准入条件未满足；需真实新鲜 runtime 快照后重跑 |
| GAP-02 | major | preset / 父子 / 深度只有自述；无 Host 元数据回读；子实例结束后补证通道被拒 |
| GAP-03 | minor | 视觉 pending：4 张图只有 2 张被子自检、1 张被父级抽查；method/sensitivity 无逐图核对；未核 PDF 页面最终字形与遮挡 |
| GAP-04 | minor | 3 类技能预检 WARN 未处理（各图 ×1，共 12 条；方法学上未达技能默认，不影响本项目 MCM 用途） |
| GAP-05 | minor | `qa-contract.md` 正文与 `stance.md` 尾部未读 |
| GAP-06 | minor | `audit_figure_collisions.py` 未用 `--strict` |
| DEV-01 | 披露 | admit_one_task=false 下仍执行 1 次 spawn（理由与边界见 §2） |
| DEV-02 | 披露 | 父级曾在项目内建 `.acceptance-tmp/pre_state.py` 记录前置哈希，事后删除；最终树中不存在 |
| DEV-03 | 披露 | 子自述写过的 `audit/live-figure/build_report.py` **在项目内 find 不到**；自述降级采信，不影响证据链 |
| DEV-04 | 披露 | 子自述曾向 `/tmp` 写 `fig_summary.py`；父级实测该文件不存在，项目文件未被触及 |

**自述可靠性实证：** 40 份产物哈希/字节全部对得上，但 `build_report.py` 与 `/tmp` 两项对不上 —— 这正是要求父级读回、不采信"工具返回成功/自报完成"的实例。

## 7. 本报告不能证明什么

- 不证明 Host 总配额、Team 成员上限或并发容量。
- 不证明 `mcm-figure` 预设内容被正确注入（只到 schema 接受 + 自述）。
- 不证明图表美观、可读性或论文页面最终视觉合格（视觉仍 pending）。
- 不产生任何比赛科学结论：数据为合成 `y'=-k*y` 演示，`synthetic=true`，不得进入论文结果。
- 不改变、不放行任何人工关口：H0_TOPIC / H1_MODEL / H2_RESULTS / H3_RELEASE **全部 pending**。

## 8. 建议下一步（由队长决定，本报告不自行登记）

1. 需要把本次结果纳入正式登记时，由队长（唯一登记写入者）写 `.mcm/tasks.json` / `artifacts.json`；本报告不自登记、不改 config。
2. 要让容量准入合格：先在真实 Host 产出 ≤60 s 的新鲜规范化 runtime 快照（含 `evidence_ref`），再重跑 spawn 步骤。
3. 要让视觉通过：由非作者逐图核对 4 张图的 PDF 与 PNG（含最终尺寸字形、图例遮挡），再更新 `visual_status` / `visual_reviewed`。
4. 若后续把 demo 图用于论文：另立排版任务复核插入尺寸；本报告不承担 H3 视觉回执。

---

**边界声明：** 本任务全程未访问、未恢复、未派发 `E:\meisai`；未改插件/profile/安全设置、未安装软件、未导出凭据或其他用户会话；`.mcm` 四登记保持 0 记录且字节未变。父级在本项目内只写本报告的 `.json` 与 `.md` 两个文件。
