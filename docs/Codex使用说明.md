# Codex 美赛团队适配候选

全局入口是 `$mcm-team`。它负责接续用户指定的美赛项目，先读项目状态和能力检查，再按任务加载角色、图表与写作参考。生成的 12 个角色与 DSH 共用科学职责和图表样式。Codex 队长统一实际派发，建模、编程、论文主管提交任务建议。角色深度为一层，专业分工仍由主管协调。

## 安装、开题和回滚

在仓库根运行下列命令。需要 Python 3.11 或更新版本。重建角色配置还需要 Node.js。

```powershell
node adapters/codex/build.mjs --check
python tools/install-codex-skill.py preview
python tools/install-codex-skill.py install
python tools/codex-project.py new --destination 'C:/MCM/新项目'
```

新项目目录必须不存在。对已有目录使用 `preview --destination` 查看差异。创建后在 Codex 打开该目录，输入“使用 $mcm-team 检查这个项目”。入口与角色以当前客户端实际加载情况为准。

安装器只管理 `~/.codex/skills/mcm-team`。它校验源文件、保留原入口，并在切换前写好事务收据。回滚时用 `python tools/install-codex-skill.py rollback --receipt <安装输出的收据路径>`。如已手动改过安装文件，先保留自己的版本。回滚会检查文件变化并归档被替换的入口。

## 协作控制和当前可用范围

```powershell
python scripts/mcm.py codex capabilities
python scripts/mcm.py codex preflight
python scripts/mcm.py codex recover
```

从新项目根运行。实际原生角色绑定与工具拦截尚未验收，候选的严格派发会明确返回阻断原因。当前聊天已验证普通子 Agent 执行和专项文件读取，派发工具没有原生角色选择字段。修改配置布尔值、给子 Agent 取同名或复制一个角色文件均无法解除严格检查。等客户端提供可核验的绑定和拦截证据后，再接入对应的运行时观察器并复验。

- 认领冻结完整任务约定，含输入、输出、写入范围和验收人。未知容量按串行处理，确认真实终态才释放记录中的占用。
- 接收时读回实际文件、依赖和审阅报告。正式文件异常改动阻止整合，入库使用新版本目录。未完成事务和遗留写锁进入恢复诊断。
- 观察到暂停后停止派发，由队长使用实际客户端的中断能力处理运行中的子任务。晚到回传保留待查。H0/H1/H2/H3 继续依赖实际用户决定。
- `scripts/codex_hook.py` 是候选的工具事件处理器。故障用例覆盖暂停与受保护路径，当前未做客户端实际注册和拒绝调用验收。文件检查约束标准协作流程，操作系统权限仍由客户端决定。
- `init-demo` 与 `--synthetic-demo` 只面向无科学成果、无人工批准的新隔离项目。演练成果保留合成标识。

## 逐小节的图表证据

为每个必要的结论小节规划一个能表达发现的图或表。问题分析可用研究路线图，假设可用条件表，求解用轨迹和误差对照，灵敏性用响应或决策变化，评价用权衡、失败情景或适用范围。多小节共用图时，各节解释自己的发现并在正文引用。必要的纯定义和文献类小节可以写明不配图理由。

按 `templates/section-visual-map.json` 填写 `paper/section-visual-map.json`。每项绑定小节锚点、结论、图表引用和源文件哈希。图表标签如定义于另一份 LaTeX 源，可在图表引用中增加同样含 path 和 sha256 的 `definition_source`。最终检查核对已声明的来源和正文引用，独立审阅核遗漏、结论表达和版面。图表设计依项目字号、尺寸和配色，从真实结果选择具有比较价值的图型。

演练说明与复现入口见[合成案例](../examples/codex-smoke/README.md)。当前客户端能力及复验范围见[候选验收记录](../audit/codex-adapter-2026-11-03/README.md)。
