# 能力、控制与验收范围

正式自动派发使用strict模式。先读实际工具schema，核验本会话是否能选择原生角色、记录真实Agent身份、确认写入路径拦截和有效容量。原生角色与hook未证实时，预检必须blocked；不得改配置verified=true绕过。

已知当前接口边界：通用协作spawn的task_name是任务名，不是native custom-agent选择。没有原生绑定字段或可核验回执时，只能证明通用子Agent执行。安装12个TOML不等于本会话热加载成功。新会话也须实测，不从版本号推断。

`init-demo`仅初始化空登记、无已批准关口、非contest的独立合成演练。显式synthetic-demo用于检查状态机和交付，不把原生角色/hook未验转为通过，不创建人工批准。正式预检被阻断时可开展用户授权的本地静态检查；不能暗中切换后台Host或其他模型服务。

能力记录分为未观察、实际观察、实际故障测试通过；角色、工具、技能、科学检查、视觉检查分别列证据。不要仅因子Agent说“我是图表手”就标原生加载通过，也不能将角色提示词中的只读要求写成操作系统隔离。

可用控制CLI：`python scripts/codex_control.py --root <project> <command>`。命令包括capabilities、preflight、claim、deliver、accept、protect、recover、status与仅新合成项目可用的init-demo；参数以该项目实际`--help`为准。

图表数值和最终页面由非作者分别检查。作者生成/自检记录保留为作者自检，不补写未执行的独立验收。暂停后到达的回报标待查；恢复必须由真实用户决定，不能因产物更新自动恢复。

官方接口参考：
- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://learn.chatgpt.com/docs/hooks
- https://learn.chatgpt.com/docs/build-skills

以上是接口依据，不是某台机器已经具备或完成验收的证明。
