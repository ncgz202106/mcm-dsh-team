# 原创科研机制与流程示意配方

这三幅图学习分类树、并行汇总、反馈闭环与可行域的视觉语法，重新设计标签、拓扑与布局，没有复制参考图的论文内容或数值。所有输出均标明 Synthetic schematic，只说明结构，不构成算法效果、模型有效性或安全性证据。

| 配方 | 用途与读图重点 | 不能据图声称什么 |
|---|---|---|
| [taxonomy](examples/taxonomy/taxonomy.png) | 用无框文字和无箭头细线组织证据层级；同层对齐 | 分类关系不等于因果、执行顺序、穷尽性或互斥性 |
| [ensemble](examples/ensemble/ensemble.png) | 共同输入到三条并行候选，再用明确的0.50/0.30/0.20权重汇总 | 仅为标量输出的示意；不是训练结果，也不证明优于单个模型 |
| [feedback](examples/feedback/feedback.png) | 动作经约束节点送到系统，观测与反馈以不同线型和端口返回；下部可行集示意提供约束的空间直觉 | 图中约束只作用于动作；可行集边界映射不是一般算法或安全保证 |

## 运行

在仓库根，沿用已安装Python、Matplotlib和Pillow环境，不联网安装或调用外部模型：

```text
python skill-overlays/nature-figure/scripts/mcm-schematics.py --recipe taxonomy --output NEW_DIRECTORY --style PROJECT/config/figure-style.json
python skill-overlays/nature-figure/scripts/mcm-schematics.py --recipe all --output ANOTHER_NEW_DIRECTORY --style bundle/src/figure-style.json
```

输出目录须不存在。`all`下每个配方各占独立子目录。默认配置取相邻`assets/mcm-figure-style.json`；颜色与字体从项目配置读取。最终宽度165.1mm；taxonomy高73.66mm、ensemble高81.28mm、feedback高96.52mm。核心字形12pt，300dpi PNG分别1950×870、1950×960及1950×1140；SVG保留可编辑文字、PDF保留矢量。

这版剔除了初稿的大圆角卡片、每框彩底、大标题和虚增留白；分类改无框细线，集成改紧凑横向，反馈保留独立回路。旧稿保存在本机，不作为活动参考。没有靠缩字或改变权重压缩画布。

这是专门的单一Python矢量路线，没有运行Fireworks生成器或其语义SVG验收。程序实际检查画布边界、节点内部文字留量、字间重叠、连接线与文字相交；科学语义和最终入稿页面仍需非作者实际审阅。维护者已看最终图，但参与此次样式修改，不能以其自检代签独立验收。

每个目录保留PDF/SVG/PNG、英文图注和`mapping.json`。映射记录真实节点、边方向、通道/关系类型、权重、布局、全部标签、源码/样式/导出哈希及机械检查范围。作者看图记录另存，不能替代独立验收。程序只会登记visual pending。

## 迁移到真实论文

先明确图要解释的主张和真实接口，再选择配方。此脚本输出固定教学拓扑，不接受生产数据或任意模型JSON；实际任务将相应绘图函数复制到任务独占目录，按当前模型重建节点、边和权重，绑定模型/结果版本，并改写图注与检查。

分类树适合背景方法分类与建模证据组织；候选汇总只在确实有组合模型及明确汇总定义时采用；闭环只有在实际存在状态、决策与反馈时使用。框架图旁边交代箭头传什么、哪一问消费什么，并让图与公式/章节对应。不要给无定义的`f(a,s)`或“安全层”擅自编算法，也不要把示意位置当测量坐标。

入稿按实际尺寸核对字号、箭头和标签。为了横向塞入而缩小，会破坏本项目12pt要求；复杂图改为纵向组织、拆图或精简到必要机制。正式论文需图表角色自检、论文负责人核表达和非作者看完整图与实际PDF。

回归：`python -m unittest discover -s tools/tests -p test_mcm_schematics.py -v`。检查实际端点身份与方向、分类非因果、权重约束、动作门通道隔离、标签完整、最终尺寸/字形/分辨率、哈希及拒绝覆盖。
