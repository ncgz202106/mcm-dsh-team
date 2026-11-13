# 四页合成布局与纠错试样

[查看PDF](presentation.pdf)。这不是完整竞赛论文，而是模板字体、三图入稿与受限修复的实际运行示范；真实论文仍用七部分功能骨架。

最终四页均经非作者实际查看。先前试样的源图标签裁切和内部大块空白被指出后，缩短同义轴名并重组短展示正文；旧失败报告保留。量值和曲线不随视觉修复改变。

本次`paper.py finish`在两轮候选之间仅把一处`1.2\linewidth`改为`\linewidth`，保持原项目不动。三张PDF和数据跨两候选哈希不变。编译、渲染及字号机械检查通过，实际视觉复验仅对这份合成试样有效，不能外推为完整模型、正式论文或人工批准。

- [运行摘要](../../../../audit/presentation-2026-11-13/runtime-summary.json)
- [最终独立复验](../../../../audit/presentation-2026-11-13/layout-runtime-final-review.json)
- [较早七页试样的真实失败报告](../../../../audit/presentation-2026-11-13/layout-runtime-review.json)

`source/paper/main.tex`与其依赖、三张PDF保留为可编译源码。安装相应TeX依赖后，从`source/paper/`用XeLaTeX或Tectonic编译；不自动安装依赖。源文件是已修复的候选。若要复验自动收窄，复制为独立项目，在`specimen-body.tex`把第一幅图设回`width=1.2\linewidth`，使用新项目的`scripts/paper.py finish`在新的输出目录运行。不要用它替换真实论文或批准记录。
