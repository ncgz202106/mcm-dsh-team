# v0.2.0 当前交付验收证据

`tools/verify-package.py`只读以下真实记录，不创建人工批准，也不自动填写视觉通过。

## audit/release-evidence.json

```json
{
  "format_version": 1,
  "bundle_version": "0.2.0",
  "source_sha256": {
    "project-template/scripts/mcm.py": "真实SHA256",
    "project-template/scripts/paper.py": "真实SHA256",
    "project-template/scripts/figure_check.py": "真实SHA256",
    "project-template/scripts/figure_demo.py": "真实SHA256",
    "project-template/config/runtime.json": "真实SHA256",
    "project-template/config/skill-routing.json": "真实SHA256",
    "project-template/config/figure-style.json": "真实SHA256",
    "project-template/paper/main.tex": "真实SHA256",
    "project-template/paper/paper-plan.json": "真实SHA256"
  },
  "native_report_sha256": "audit/native-runtime-smoke.json真实SHA256",
  "artifacts": [
    {"path": "diagrams/01-role-architecture.svg", "sha256": "真实SHA256", "purpose": "可编辑角色架构图"}
  ],
  "figure_contracts": [
    {"project_root": "rehearsal", "path": "figures/figure-demo/method.contract.json", "sha256": "真实SHA256"},
    {"project_root": "rehearsal", "path": "figures/figure-demo/comparison.contract.json", "sha256": "真实SHA256"},
    {"project_root": "rehearsal", "path": "figures/figure-demo/sensitivity.contract.json", "sha256": "真实SHA256"},
    {"project_root": "rehearsal", "path": "figures/figure-demo/uncertainty.contract.json", "sha256": "真实SHA256"}
  ],
  "paper_build": {
    "project_root": "rehearsal",
    "pdf": "build/paper/demo.pdf",
    "manifest_sha256": "demo.build.json真实SHA256",
    "pdf_sha256": "demo.pdf真实SHA256"
  },
  "visual_review_ref": {"path": "audit/visual-inspection.json", "sha256": "真实SHA256"}
}
```

示例展示字段，并非可直接验收的记录。`source_sha256`至少包含示例九项以及tools/update-dsh.ps1、tools/restore-dsh.ps1、tools/dsh-install-common.ps1、tools/test-install.ps1四项安装源，也可以覆盖更多源文件。所有路径相对包根或其指定project_root，不允许越界。演练目录名可改变。

`artifacts`必须包括三张架构图各自SVG、PNG、JSON；四张演练图的PDF、SVG、PNG；演练PDF及其build manifest。其他源码、图表契约、数据、QA报告也宜加入。四份图表契约会重新执行当前figure_check，演练PDF会执行非release paper check；不放松synthetic或人工关口。演练mcm/paper/figure_check/figure_demo脚本须与当前模板一致，防止用旧演练证明新版本。

## audit/visual-inspection.json

```json
{
  "format_version": 1,
  "bundle_version": "0.2.0",
  "checked_at": "实际检查时间",
  "reviewer": "实际汇总者身份",
  "human_confirmation": false,
  "passed": true,
  "images": [
    {
      "path": "diagrams/01-role-architecture.png",
      "sha256": "实际查看图片SHA256",
      "author_agent_ids": ["实际作者身份"],
      "checked_by": "实际非作者复核者身份",
      "checked": ["标签完整", "无裁切", "无重叠", "文字可读", "箭头语义正确"]
    }
  ]
}
```

images覆盖三张架构PNG、四张单独图PNG和当前PDF的每一张渲染页。checked_by不能属于该图author_agent_ids。须实际查看后填写，不能只看脚本返回值；审美与数学核验记录如有缺口应保留pending，不伪造pass。该记录是AI验收证据，不冒称真人确认；论文正式发布仍走独立的H2/H3与paper视觉门禁。

## 原生runtime记录

`audit/native-runtime-smoke.json`必须由真实隔离runtime执行产生：status passed、每项checks passed、registry覆盖12个精确role IDs。bundle_file_sha256覆盖package/patch/provenance及presets/build/native-plan/skill-routing/archive三模块；prompt_sha256覆盖shared与12角色。空fingerprint、旧v0.1记录或任一当前源变更均不能验收。
