# Codex 协作合成演练

[演示论文](paper.pdf) 用一个带恒定损耗的 logistic 方程演练模型交接、数值验证、图表溯源和论文排版。全部参数为合成设定，证据范围限于本例。九组参数的逐时最小值和最大值给出参数包络，没有给这些参数分配概率。

## 查看交付件

- [模型契约](model-contract.json) 和 [求解交接](solver-handoff.json) 固定了接口、参数与误差阈值。四阶 Runge–Kutta 求解器位于 [solver.py](solver.py)。
- [冻结数据清单](evidence/data-manifest.json) 记录实际生成的四份 CSV、论文数字、数值检查和输入文件哈希。[数值检查](evidence/validation.json) 包括解析解对照、步长减半、零初值和增长率等于损耗率的边界。
- [出图清单](evidence/figures/figure-manifest.json) 记录 PDF、SVG 和 300 DPI PNG。每张图旁的映射记录注明 CSV、列、行群、变换、坐标范围与机械检查。
- [章节配图映射](paper/section-visual-map.json) 关联正文的五个必要章节与各自的流程图、参数表、轨迹图、敏感性图和参数包络图。
- [独立复核](independent-demo-review.json) 记录最终 PDF、逐页核查、解析解重算和图表数据校验。
- [构建核验](evidence/build-verification.json) 记录实际使用的 Tectonic 版本、27 项单元测试、10 项数值检查、图表在正文中的字号和四页目视检查。

本例的普通协作分工与原生自定义角色的运行证据分开记录。任何 H0/H1/H2/H3 人工批准都须另有真实记录。

## 复现

从仓库根目录运行以下 PowerShell 命令。需要 Python、Matplotlib、Tectonic 和 Poppler 的 `pdftoppm`。使用 Codex 自带的 Tectonic 时，把命令中的 `tectonic` 换为该可执行文件的路径。实验入口会拒绝覆盖已有输出。安装了 Nature Figure 检查脚本和 PyMuPDF 时，可在实验命令追加 `--qa-scripts <脚本目录>`，以运行导出图的对齐、字形和碰撞检查。

```powershell
python -B -m unittest discover -s examples/codex-smoke -v
if ($LASTEXITCODE -ne 0) { throw "Demo tests failed" }

$example = (Resolve-Path examples/codex-smoke).Path
$scratch = Join-Path ([IO.Path]::GetTempPath()) ("codex-smoke-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $scratch | Out-Null
Push-Location $scratch
try {
    python -B "$example/experiments.py" --output evidence
    if ($LASTEXITCODE -ne 0) { throw "Experiments failed" }
    Copy-Item "$example/paper.tex" evidence/paper.tex
    Set-Location evidence
    tectonic -X compile --untrusted paper.tex
    if ($LASTEXITCODE -ne 0) { throw "Tectonic build failed" }
    pdftoppm -r 150 -png paper.pdf page
    if ($LASTEXITCODE -ne 0) { throw "Page rendering failed" }
    Get-Item paper.pdf
} finally {
    Pop-Location
}
```

图和文稿以冻结数据中的数值为准。运行时间、软件版本和 PDF 元数据可能影响重新构建的文件哈希。逐页查看新生成的 PNG，以核对排版、字号和图表内容。
