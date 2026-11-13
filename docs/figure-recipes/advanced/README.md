# 有条件使用的三维科研图

这两种原创配方只在第三维有科学含义时启用。图内和数据映射均明确标记合成示范；不是任何论文的真实结果，也不是已验收的模型。只依赖已有的 NumPy 和 Matplotlib，不自动安装软件或调用网络。

| 论证任务 | 配方与参照 | 适用条件 | 应改用二维图的情况 |
| --- | --- | --- | --- |
| 两个输入共同怎样改变一个响应 | [surface](surface/surface.png)：响应曲面与同数据等高图 | 具有明确单位的完整实算网格；需要看局部梯度、交互或形状 | 只有一个输入、响应恒定，或等高图已能完整表达判断 |
| 水平位置相近时是否处在不同高度 | [trajectory](trajectory/trajectory.png)：真实三维位置与 XY/XZ 投影 | x/y/z 均有物理意义、单位均为米，且位置不共面 | 把时间挤成假 z 轴、将柱形挤成立体，或真实轨迹是平面的 |

每幅图宽 165.1 mm、高 228.6 mm，核心文字最低 12 pt，PNG 为 1950 × 2700、300 dpi；PDF/SVG 保留矢量及可编辑文字。入稿必须按此实际宽度使用，缩图会破坏字号要求。面板多而页面放不下时应拆图。

## 运行与输入

在仓库根运行，输出目录必须尚不存在：

```text
python skill-overlays/nature-figure/scripts/mcm-advanced.py --recipe surface --output NEW_SURFACE --style bundle/src/figure-style.json
python skill-overlays/nature-figure/scripts/mcm-advanced.py --recipe trajectory --output NEW_TRAJECTORY --style bundle/src/figure-style.json
python skill-overlays/nature-figure/scripts/mcm-advanced.py --recipe surface --output NEW_REAL_DATA --style PROJECT/config/figure-style.json --data FROZEN_RESULTS.csv
```

不带 `--data` 时生成固定、原创、可复算的合成数据。带 `--data` 时原样保留 CSV 字节和 SHA-256，并标记“外部 CSV，来源未核验”，不自动把输入宣称为实测值。

- `surface` 精确列头：`x_m,y_m,response_kPa`。每个 x/y 组合恰好一行，至少 3 × 3；允许非均匀间隔，不允许重复、缺失或非有限值。不在图中填补网格、不聚合重复点、不外推。原始点同时保留在曲面与平面中，曲面面片和等高线只是网格值之间的展示插值，不能称为新的测量。
- `trajectory` 精确列头：`time_s,x_m,y_m,z_m`。时间严格递增；不自动排序、合并或删行。三个空间坐标均须变化，且整体坐标矩阵须非平面。原始点全部保留，线段仅连接相邻输入，不证明中间位置、速度或避障安全。

更换单位时必须同时改数据契约、轴名、图注与校验，不能只改 CSV 列名。不要给示范数据去掉 Synthetic 标签就充当正式结果。真实输入的测量/模拟来源、误差、缺失处理和科学主张仍由上游验证。

## 相机、颜色与几何

使用正交投影，固定仰角 28°、方位角 −128°，避免把透视远近误当数值变化。相机位置影响遮挡，不能据一个视角判定路径不相交；轨迹配有 XY/XZ 参照。

`surface` 颜色与高度均编码同一 kPa 响应，两个面板使用相同 cividis 范围，不裁剪；平面保持 x/y 等比例，立体高度不是空间长度。`trajectory` 颜色只编码秒数，所有面板共用时间范围，三个空间维度等比例且采用同一米制轴域。XY 投影出现重合点时，XZ 与共同时间编码用于区分高度，不抖动真实坐标。

每个输出目录含 CSV、PDF、SVG、PNG、英文图注及 `mapping.json`。映射记录单位、全部面板职责、归一化范围、相机、几何比例、尺寸、代码/样式/数据/导出哈希及 QA 状态。

## 检查与边界

可通过 `--qa-scripts PATH_TO_NATURE_FIGURE/scripts` 指向已安装的图表检查助手；相邻安装已有助手时自动使用。缺少助手明确登记未执行，不能当成检查通过。助手碰撞检查有 FAIL 时本次导出失败；WARN 仍需逐项看图。

此处两套最终产物均已检查 PDF 字高，最小 12 pt，没有低于阈值的文字；两套碰撞报告均为 0 FAIL、2 WARN。XY/XZ 投影的实际绘图区对齐检查 PASS。曲面与等高图的形状和物理职责不同，对齐助手明确报 NOT AUDITABLE；没有把它包装为对齐通过。作者实际看图记录和警告解释在 [visual-review.md](visual-review.md)，不代表独立审稿或科学验收。

回归检查：`python -m unittest discover -s tools/tests -p test_mcm_advanced.py -v`。八项检查覆盖数据保留、错误单位、缺失/重复格点、额外 CSV 单元格、时间顺序、平面伪三维、颜色映射、等比例、物理尺寸、PNG 分辨率与覆盖保护。静态预检无 FAIL；其 PNG/TIFF、300/600 dpi 和动态尺寸警告按本项目的 PDF/SVG/300 dpi、165.1 mm 合同解释，以真实导出和尺寸测试核验。
