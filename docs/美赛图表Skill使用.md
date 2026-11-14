# 美赛图表Skill如何复用

以后在MCM任务中使用`nature-figure`，会先进入MCM分支，再按当前问题读取1–2条视觉配方。已经选择的Python/R后端保持；本次可运行样例提供Python版，R任务参考布局并由R重画，不偷换后端。

不需要每次重新提供原始写作资料。自编的图型选择、图文协作、样式和示例随Skill安装；原资料与原论文留在本机，不进入公开包。可参考的样例包括预测与残差、敏感性与决策、Pareto权衡、配对分布、共享轴策略、共享色标网格。网络、守恒流与方法图在确有任务需要时按专门说明制作。

机制/框架、符号情景、分类、集成、反馈和计数/组成图，按需读取[科研图视觉语法](../skill-overlays/nature-figure/references/mcm-scientific-grammar.md)。它提炼颜色/形状分工、重复组件对齐、独立反馈通道和明确分母；对抽象关系保持二维清晰，真实第三变量仍走条件3D路线。没有独立测量的区域和点位置只作示意。

## 给Agent的任务示例

> 用nature-figure的MCM分支，根据当前冻结结果制作比较图。先说明主结论、参照和互补面板，按mcm-visual-recipes选择合适布局，读取本项目figure-style。保持全部有效样本、单位和区间定义，交源码、PDF/SVG/PNG、英文图注和数据映射；检查最终入稿尺寸与整页效果。

论文负责人先派图表简报，再核粗图；图表手核数后精修；审阅者实际看图与页面。缺少所需指标/区间时，转给建模、编程和验证角色，不能用图库样例填结果。

## 可直接查看的样例

以下全部使用合成数据。每幅旁边保留SVG、数据JSON、英文图注与面板说明；不要当作参赛结果。

| 样例 | 预览 | 矢量图 |
| --- | --- | --- |
| 预测与残差 | [PNG](figure-recipes/prediction.png) | [PDF](figure-recipes/prediction.pdf) |
| 敏感性与决策 | [PNG](figure-recipes/sensitivity.png) | [PDF](figure-recipes/sensitivity.pdf) |
| Pareto与备选 | [PNG](figure-recipes/pareto.png) | [PDF](figure-recipes/pareto.pdf) |
| 配对分布与ECDF | [PNG](figure-recipes/paired.png) | [PDF](figure-recipes/paired.pdf) |
| 共享轴策略小图 | [PNG](figure-recipes/strategies.png) | [PDF](figure-recipes/strategies.pdf) |
| 共享色标网格 | [PNG](figure-recipes/spatial.png) | [PDF](figure-recipes/spatial.pdf) |

## 独立试用

新增两类原创起点：分类/集成/反馈见[机制示意](figure-recipes/schematics/README.md)，情景分面和计数/组成见[证据面板](figure-recipes/evidence-panels/README.md)。均导出矢量PDF、可编辑SVG与300dpi PNG；图中标明合成或示意，真实任务须替换并核对模型接口/固定数据。

在仓库根使用现有Python、NumPy、Matplotlib：

```text
python skill-overlays/nature-figure/scripts/mcm-gallery.py --recipe paired --output NEW_DIRECTORY --style project-template/config/figure-style.json
```

`--recipe all`生成六种；默认拒绝覆盖已有目录。图注、数据和图源输出在同一目录。安装后可从nature-figure的`scripts/mcm-gallery.py`运行，默认发现原Skill的检查脚本；从仓库直接运行时可用`--qa-scripts INSTALLED_SKILL/scripts`显式指定。缺检查工具会记录未执行，不登记视觉验收。

样式唯一源为`bundle/src/figure-style.json`；运行`node bundle/src/build.mjs --sync-project-style`同步新项目和Skill的默认配置。项目已经确认的样式优先，导出物理宽度不能在入稿时任意缩小后仍声称12pt。

## 更新和恢复

现有`tools/skill-overlays.py`在原有五个MCM引用基础上支持显式列出的MCM参考、脚本和样式资源。先只读预检，再带独立备份目录应用，回滚会校验当前字节，保留之后用户修改。通用上游Skill入口、模型、权限和角色层级保持。

源码同步不等于DSH已安装。用户当前采用Codex本地执行，本维护不启动DSH、不修改暂停演练，也不代签科学结果或论文批准。测试、实际看图和未来每个任务的独立验收分别记录；不存在保证获奖或对任意数据自动达到固定审美水平的模板。
