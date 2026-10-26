# 角色与专项Skill

12类预设不是12个常驻Agent。默认按阶段轮换，并根据真实Host容量限制实例数。角色专长是提示词/任务政策；全局工具权限须另做运行时读回。

| 角色ID | 工作及默认专项路由 |
|---|---|
| mcm-captain | 唯一内部调度/登记，按需工作包协调Codex，无强制主Skill |
| mcm-model-lead | 统一模型接口；统计设计缺口才用nature-statistics |
| mcm-modeler | 独立候选与反证；按需nature-statistics |
| mcm-evidence | nature-academic-search检索；nature-ref-verifier核验；nature-downloader按需全文 |
| mcm-programmer | 两实例求解/实验导出；统计输出专项才用nature-statistics |
| mcm-code-lead | 可选且默认不启动，只在明确集成任务与配额下派programmer |
| mcm-verifier | 独立复现及适用的nature-statistics、引用核验 |
| mcm-paper-lead | nature-writing generic整合，nature-polishing精简；唯一主稿写入者 |
| mcm-writer | 按分区写章节，不覆盖主稿；通用英文写作与润色 |
| mcm-figure | 定量nature-figure，方法/几何/流程fireworks-tech-graph |
| mcm-typesetter | 现有latexmk+XeLaTeX构建；pdf渲染/逐页审查 |
| mcm-reviewer | nature-reviewer独立审阅，以MCM任务/规则/内部量表评价 |

## 一次技能任务怎样落地

1. 父层给目标、版本化输入、写分区、结果/图表契约、主Skill和验收。
2. 子Agent核实际角色与工具，再读取对应SKILL.md和必要分支；不要整目录预载。
3. 记录来源路径、哈希、主Skill/分支、工具和依赖可用性。沿用项目已选Python/R，不逐图重复问。
4. 执行真实命令并保存退出状态、输出位置/哈希及失败限制。Skill已读不等于执行成功。
5. 下游读回指定产物，按核数/表达/页面/独立审阅分工验收。没有实际看图、看页，不登记视觉通过。

每任务选一个主Skill，辅助只围绕具体缺口。缺技能或依赖就报告，不能伪造工具调用成功或自动降标准。项目导出config/skill-routing.json来自bundle/src/skill-routing.mjs；修改路由源后重新导出和构建。

## 不自动调用的流程

shumo2、shumo2-v2、shumo-core、askill、askill-v2、math-modeling、mathematical-modeling、paper-spine等全流程总控不自动启动，专项Skill的间接引用也不能绕过。叶子需要额外Agent时向父层请求，不因Skill建议就越级派发。

nature-citation限定Nature/CNS，不作MCM默认检索；nature-data不是通用数据清洗；venue-templates不替换已有MCM骨架。Skill不增加写入/发布/恢复权限，不修改用户结构或竞赛规则。

## 图表验收重点

定量图绑定明确run_id/版本/字段/单位，新增估计、筛选或指标回编程/建模确认。方法示意通常1–2张，数值图按论证价值配置。核心文字按最终入稿尺寸12pt，图例无挡线、面板对齐、误差含义清楚、配色与线型一致，输出可编辑源和英文图注。

编程/验证核数，论文负责人核表达，排版核实际PDF，非作者独立看完整图与最终页。作者自检必须做，但不能自签独立验收。借鉴用户优秀论文的布局和证据组织，不复制其内容与数据。
