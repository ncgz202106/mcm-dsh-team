# 启动与接续

全局入口安装后，Skill目录的`.mcm-skill-install.json`保存本机`source_root`及安装字节信息。它是本机定位记录，不上传。读取并确认source_root仍含tools/codex-project.py与adapters/codex/generated/manifest.json；失效时报告路径缺口，重新安装或修复定位，不搜索凭据或启动其他平台。

新项目：`python <source_root>/tools/codex-project.py new --destination <绝对新目录>`。目标已经存在时必须拒绝；要查看已有项目差异使用`preview --destination <目录>`，该命令只读，不升级旧成果或批准记录。

在新目录打开Codex，读AGENTS.md和protocols/08-codex-readiness.md。角色配置位于`.codex/agents/`；实际加载以本会话工具及真实回执为准，不能仅看磁盘文件。工具未提供原生role参数或无法核验时记录blocked，不冒称已启动该角色。

队长先执行`python scripts/codex_control.py --root <项目根> capabilities`和`preflight`。完整参数请读该项目`--help`。控制脚本仅支持在已授权范围内认领/交付/接收/恢复；技术通过不生成H0/H1/H2/H3批准。

既有项目接续：先读当前状态、有效候选及未关闭问题，校验protect/recover报告。不要重跑已验结果来例行证明“继续”，不要把全量聊天历史塞入每个子任务。

需要上游Nature或绘图/PDF技能时，先查实际可用Skill。上游完整包未随本入口分发，缺失时明确报告。可以读取本包自编参考材料，但不能因此登记“已执行nature-figure”。
