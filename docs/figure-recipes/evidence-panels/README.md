# 符号情景与计数证据面板

两种原创Python配方提炼分面、颜色/形状分工、共同图例和直接读数。默认都是Synthetic demonstration，没有复制参考图的数值、原文或图像。

| 配方 | 预览 | 用途 |
|---|---|---|
| scenarios | [PNG](scenarios/scenarios.png)、[PDF](scenarios/scenarios.pdf) | 颜色=来源、形状=类别、填充=当前步骤可用性；三个面板同位置比对，位置和圆面积不是测量值 |
| counts | [PNG](counts/counts.png)、[PDF](counts/counts.pdf) | 年份×类别的非负计数矩阵配完整年组成条形；顺序色标与数字供读数，空圈0和方框NA分开 |

沿用已选Python后端，不安装依赖或调用网络：

```text
python skill-overlays/nature-figure/scripts/mcm-evidence-panels.py --recipe scenarios --output NEW_SCENARIOS --style PROJECT/config/figure-style.json --qa-scripts INSTALLED_NATURE_FIGURE/scripts
python skill-overlays/nature-figure/scripts/mcm-evidence-panels.py --recipe counts --output NEW_COUNTS --style PROJECT/config/figure-style.json --data FROZEN_COUNTS.json
```

固定JSON结构见各例`source.json`和脚本`validate_data`。可选`--data`原样保留输入字节；来源仍标未核验，不因文件被读取就成为实测或已验收结果。输出目录已有时拒绝覆盖。PDF、可编辑文字SVG、300dpi PNG、英文图注、数据、映射与QA分开保存。

`scenarios`的Target拟合子集与评估子集是不同ID。面板b只让拟合子集进入可用集合，面板c仅激活独立评估子集；其余点保持空心。它说明信息角色，不证明任何训练算法有效。图中所有域位置是排版坐标，不能读出距离、泛化误差或概率。

`counts`用常量大小点及顺序色阶表示计数，同时标出精确数字。2021有缺失，组成统计整年排除，包含其已知单元格也不参与；2022–2024合计37项，四类分别13、10、9、5。类别在示例中声明互斥且穷尽；这不是从图上推断出的事实。汇总比例不是年度比例的均值，更不能作为趋势或因果结论。真实数据须核去重、窗口与类别定义。

最终宽165.1mm，图内最小12pt；复杂标签需重排而非缩小。`scenarios`同坐标面板做实际对齐检查，`counts`两个不同职责坐标面板不冒称可比轴对齐通过。数值色阶仍用于数据编码，保持简洁标题、直接标签和共同分母，不使用装饰渐变、荧光色或立体饼图。

实际看图不等于已审查真实论文；未来入稿还须检查最终缩放、图注、引用及整页效果。作者/维护者记录与非作者验收分开。

当前两例的[非作者复核](../../../audit/scientific-grammar-2026-11-14/evidence-independent-review.json)已检查图像、目标拟合/评估ID隔离及组成的13/37、10/37、9/37、5/37；通过范围为合成配方参考用途。
