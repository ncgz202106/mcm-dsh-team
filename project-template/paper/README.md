# LaTeX 论文工程

`main.tex` 是正式写作骨架，包含有意保留的 DRAFT 指引；`demo.tex` 是明确标注 SYNTHETIC 的演练稿。二者均不能直接作为参赛论文提交。

在项目根执行：

```powershell
python scripts/figure_demo.py --skill-root "实际已安装的nature-figure目录"
python scripts/paper.py build --demo
python scripts/paper.py build
python scripts/paper.py check build/paper/demo.pdf
```

在独立新项目先运行 `figure_demo.py` 生成四图演练（1方法总览、结果对照、灵敏性和参数包络），默认 `figures/figure-demo/` 存在时 `demo.tex` 使用新版示范。目录存在即拒绝覆盖，保留已有证据。未提供 skill-root 时只执行本项目审计，不能宣称执行了nature-figure。旧 `mcm.py demo` 的allocation示例仅作兼容回退。

编译输出放在 `build/paper/`，不混入章节源码。构建使用 XeLaTeX 和 BibTeX，由 latexmk 处理重复运行；Windows 若缺少 PATH 中的 Perl，会检查 Git 自带 Perl，仅补入构建子进程环境。

主报告与 AI 报告在同一个 PDF 中。`main-report-end` 标签位于主报告最后一页，检查器依此计算主报告页数；AI 报告从下一页开始。页数不会通过把参考文献或附录移至 AI 报告规避。默认队号 `0000000`、DRAFT 指引和演练标识都会在发布检查中被拦截。

论文负责人是 `main.tex`、`team.tex`、主章节和 `references.bib` 的唯一整合者。写作子 Agent 在任务卡指定的独立子稿目录交付；排版子 Agent 负责样式、构建与检查报告，主文件修改先交论文负责人整合。`paper/generated/` 的数值由求解导出流程生成，不手工改数。

## 官方模板来源及改动

`provenance/MCM-ICM_Summary.tex` 保留 2026-10-24 下载的官方原文件及工具初始化生成的 `latex-project.json`。来源为 COMAP 的 2027 规则页所链接的 LaTeX Summary Sheet。

原文件头部写2027，但可见摘要标题仍写2026；本工程依据2027规则改为可配置的2027。为匹配已确定的 XeLaTeX 流程，移除原 `graphicx` 的 `pdftex` 固定驱动。保留官方 article 12pt、页边距、newtx 字体与 Summary Sheet 三栏信息结构；扩展章节化输入、统一页眉、引用和单独 AI 报告。没有将此衍生工程称为官方完整模板。

加入 xeCJK 与 TeX 自带 Fandol 字体以原样呈现 AI 报告中的中文查询，正式论文主体仍为英文。生成披露 fragment 可运行 `python scripts/ai_report.py --root . --archive logs/ai-audit/实际目录 --output paper/ai-use/report-v1.tex`；检查 coverage 和真实核验记录，再由论文负责人整合到 `ai-use/report.tex`。片段不重复 Report 标题。

自动检查不能代替逐页视觉检查；最终发布要求独立审阅、实际人工确认及当前有效证据。

`paper-plan.json` 的 `figures` 记录每张图的 `figure_id` 与 `contract_ref:{path,sha256}`；构建固化为 `figure_refs`，发布检查重新读回契约、数据、脚本和QA文件。输入改动使原图/原PDF失效。图表可用 `figure_demo.new_plot_canvas(style, panels=1/2)` 创建单图或上下双面板画布；默认165.1mm宽，双面板实际导出仍需运行技能对齐与碰撞审计。
